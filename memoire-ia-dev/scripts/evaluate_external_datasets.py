"""Evaluate derived external corpora using AIDev PR metadata as an offline cache."""

from __future__ import annotations

import json
import math
import sys
import tarfile
import zipfile
from pathlib import Path

import pandas as pd

from memoire_ia_dev.validation import evaluate_aidev_full, load_aidev


ROOT = Path(__file__).resolve().parents[1]
EXTERNAL = ROOT / "data" / "external"
OUTPUT = ROOT / "data" / "processed" / "external_dataset_validation_report.json"


def canonical_url(values: pd.Series) -> pd.Series:
    return values.astype("string").str.rstrip("/").str.lower()


def json_ready(value):
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def load_agenticflict() -> pd.DataFrame:
    with tarfile.open(EXTERNAL / "agenticflict.tar.gz", "r:gz") as package:
        source = package.extractfile("data/clean/agenticflict_pr_clean.csv")
        if source is None:
            raise ValueError("AgenticFlict PR table is missing")
        records = pd.read_csv(source, usecols=["repo_full_name", "pr_number", "agent"])
    records["html_url"] = (
        "https://github.com/" + records["repo_full_name"] + "/pull/" + records["pr_number"].astype(str)
    )
    return records


def load_test_coverage() -> tuple[pd.DataFrame, pd.DataFrame]:
    prefix = "replication-package/data/test_detection/"
    with zipfile.ZipFile(EXTERNAL / "test_coverage_prs.zip") as package:
        positives = pd.concat([
            pd.read_csv(package.open(prefix + "ai_only_prs_test_detection.csv")),
            pd.read_csv(package.open(prefix + "coauthor_prs_test_detection.csv")),
        ], ignore_index=True)
        humans = pd.read_csv(package.open(prefix + "human_prs_test_detection.csv"))
    return positives, humans


def hydrate(reference: pd.DataFrame, aidev: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    requested = reference.copy()
    requested["join_url"] = canonical_url(requested["html_url"])
    metadata = aidev[["number", "title", "body", "user", "agent", "html_url"]].copy()
    metadata["join_url"] = canonical_url(metadata["html_url"])
    metadata = metadata.drop_duplicates("join_url")
    hydrated = requested.merge(
        metadata.drop(columns=["agent", "html_url"]), on="join_url", how="left", validate="many_to_one",
    )
    available = hydrated["number"].notna()
    return hydrated.loc[available].copy(), {
        "n_reference": int(len(requested)),
        "n_hydrate": int(available.sum()),
        "n_absent_aidev": int((~available).sum()),
    }


def evaluate_positive_dataset(
    reference: pd.DataFrame, aidev: pd.DataFrame, name: str, version: str,
) -> dict[str, object]:
    hydrated, coverage = hydrate(reference, aidev)
    report, _ = evaluate_aidev_full(hydrated, version=version)
    report["dataset"] = name
    report["hydratation"] = coverage
    report["independance"] = (
        "Les metadonnees d'entree proviennent d'AIDev; ce test mesure un sous-ensemble derive, "
        "pas une replication independante."
    )
    return report


def main() -> None:
    aidev = load_aidev()
    agenticflict = load_agenticflict()
    test_coverage, humans = load_test_coverage()

    report = {}
    for version in ("v1", "v2"):
        report[version] = {
            "agenticflict": evaluate_positive_dataset(agenticflict, aidev, "AgenticFlict", version),
            "test_coverage_positifs": evaluate_positive_dataset(
                test_coverage, aidev, "MSR 2026 Test Coverage - positifs IA et co-auteurs", version,
            ),
        }
    human_matches, human_coverage = hydrate(humans, aidev)
    report["test_coverage_humains"] = {
        **human_coverage,
        "n_aussi_labelle_positif_aidev": int(len(human_matches)),
        "precision_calculable": False,
        "raison": (
            "AIDev ne fournit les metadonnees que pour ses positifs. Les autres PR humaines "
            "restent sans titre, corps, auteur ou branche hors ligne."
        ),
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    report = json_ready(report)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=True, indent=2, allow_nan=False), encoding="utf-8")
    json.dump(report, sys.stdout, ensure_ascii=True, indent=2, allow_nan=False)
    print()


if __name__ == "__main__":
    main()