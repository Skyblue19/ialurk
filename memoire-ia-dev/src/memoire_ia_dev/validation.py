"""AIDev import and transparent comparison with explicitly attributed records."""

from __future__ import annotations

from typing import Iterable
from urllib.parse import urlparse

import pandas as pd

from .prs import _match_agent_login, detect_pr_attribution


def load_aidev(config: str = "all_pull_request", split: str = "train") -> pd.DataFrame:
    """Download a named AIDev table only when requested, preserving its schema."""
    try:
        from datasets import load_dataset
    except ImportError as error:
        raise RuntimeError("Install dataset dependencies with: pip install -e '.[datasets]'") from error
    return load_dataset("hao-li/AIDev", config, split=split).to_pandas()


def normalize_aidev_pull_requests(reference: pd.DataFrame) -> pd.DataFrame:
    """Normalize the observed AIDev PR schema for transparent ID-based matching."""
    required = {"number", "repo_url", "agent"}
    missing = required - set(reference.columns)
    if missing:
        raise ValueError(f"AIDev table is missing required columns: {sorted(missing)}")
    result = reference.copy()
    result["depot"] = result["repo_url"].map(_repository_from_api_url)
    result["identifiant"] = result["number"].astype(str)
    result["outil_reference"] = result["agent"]
    return result[["depot", "identifiant", "outil_reference"]]


def _repository_from_api_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    prefix = "repos/"
    if not path.startswith(prefix) or len(path.removeprefix(prefix).split("/")) != 2:
        raise ValueError(f"Unexpected AIDev repository URL: {url}")
    return path.removeprefix(prefix)


def compare_to_reference(
    extracted: pd.DataFrame,
    reference: pd.DataFrame,
    identifier_column: str,
    reference_identifier_column: str,
) -> dict[str, int | float | None]:
    """Compare detector output with a reference's positive identifiers.

    Unlabelled records are presumed negatives only for this operational estimate.
    """
    confirmed = set(reference[reference_identifier_column].dropna().astype(str))
    observed_ids = extracted[identifier_column].astype(str)
    reference_positive = observed_ids.isin(confirmed)
    detected = extracted["ai_attribue"].fillna(False).astype(bool)
    true_positive = int((reference_positive & detected).sum())
    false_negative = int((reference_positive & ~detected).sum())
    false_positive = int((~reference_positive & detected).sum())
    return {
        "vrai_positif": true_positive, "faux_negatif": false_negative, "faux_positif": false_positive,
        "rappel": true_positive / (true_positive + false_negative) if true_positive + false_negative else None,
        "precision": true_positive / (true_positive + false_positive) if true_positive + false_positive else None,
    }


def evaluate_aidev_full(reference: pd.DataFrame, commits: pd.DataFrame | None = None) -> tuple[dict[str, object], pd.DataFrame]:
    """Evaluate the PR detector against every positive row in an AIDev table.

    AIDev is a positive reference corpus. Therefore this function reports recall,
    not precision: its rows do not represent all non-agent GitHub PRs.
    Passing the `pr_commits` table enables the committer-identity signal.
    """
    required = {"number", "title", "body", "user", "agent"}
    missing = required - set(reference.columns)
    if missing:
        raise ValueError(f"AIDev table is missing required columns: {sorted(missing)}")

    records = reference[["number", "title", "body", "user", "agent"]].copy()
    records["committer_login"] = _committer_lookup(reference, commits)
    records["donnees_commit"] = (
        reference["id"].isin(set(commits["pr_id"]))
        if commits is not None and "id" in reference.columns
        else False
    )
    records["detected"] = records.apply(
        lambda row: detect_pr_attribution({
            "author_login": row["user"], "committer_login": row["committer_login"],
            "title": row["title"], "body": row["body"],
        }) is not None,
        axis=1,
    )
    records["outil_reference"] = records["agent"]
    by_agent = records.groupby("outil_reference", dropna=False).agg(
        n_reference=("number", "size"),
        n_detecte=("detected", "sum"),
        rappel=("detected", "mean"),
        couverture_donnees_commit=("donnees_commit", "mean"),
    ).reset_index()
    with_commits = records.loc[records["donnees_commit"]]
    conditional = with_commits.groupby("outil_reference", dropna=False)["detected"].mean()
    by_agent["rappel_si_donnees_commit"] = by_agent["outil_reference"].map(conditional)
    report: dict[str, object] = {
        "dataset": "hao-li/AIDev/all_pull_request",
        "signal_committer": commits is not None,
        "n_reference": int(len(records)),
        "n_detecte": int(records["detected"].sum()),
        "rappel_global": float(records["detected"].mean()) if len(records) else None,
        "precision": None,
        "precision_interpretation": "Non calculable sur AIDev seul: le dataset ne contient pas les PR negatives.",
        "rappel_par_outil": by_agent.to_dict("records"),
    }
    return report, records


def _committer_lookup(reference: pd.DataFrame, commits: pd.DataFrame | None) -> pd.Series:
    """Map each PR to a commit identity that matches a known agent, when available."""
    if commits is None or "id" not in reference.columns:
        return pd.Series([None] * len(reference), index=reference.index, dtype="object")

    identities = pd.concat([
        commits[["pr_id", "committer"]].rename(columns={"committer": "login"}),
        commits[["pr_id", "author"]].rename(columns={"author": "login"}),
    ]).dropna()
    identities = identities.loc[identities["login"].map(lambda login: _match_agent_login(str(login)) is not None)]
    mapping = identities.drop_duplicates("pr_id").set_index("pr_id")["login"]
    return reference["id"].map(mapping)


def select_reference_repositories(reference: pd.DataFrame, repository_column: str, candidates: Iterable[str]) -> pd.DataFrame:
    """Return only AIDev rows intersecting the study's candidate repositories."""
    return reference.loc[reference[repository_column].isin(set(candidates))].copy()