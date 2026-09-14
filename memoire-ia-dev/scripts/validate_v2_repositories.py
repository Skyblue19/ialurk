"""Validate detector V2 against the eight locally collected PR datasets."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from memoire_ia_dev.prs import tag_prs


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUTPUT = ROOT / "Resultats" / "validation_v2_huit_depots.json"
REPOSITORIES = {
    "microsoft/vscode": "microsoft_vscode_prs.csv",
    "home-assistant/core": "home-assistant_core_prs.csv",
    "vercel/next.js": "vercel_next.js_prs.csv",
    "godotengine/godot": "godotengine_godot_prs.csv",
    "redis/redis": "redis_redis_prs.csv",
    "django/django": "django_django_prs.csv",
    "ppy/osu": "osu_prs_2020_2026.csv",
    "oven-sh/bun": "bun_prs_2020_2026.csv",
}


def validate_repository(repository: str, filename: str) -> dict[str, object]:
    path = RAW / filename
    if not path.exists():
        raise FileNotFoundError(f"Missing PR dataset for {repository}: {path}")

    source = pd.read_csv(path, low_memory=False)
    v1 = tag_prs(source, version="v1")
    v2 = tag_prs(source, version="v2")
    lost_v1 = v1["ai_attribue"] & ~v2["ai_attribue"]
    new_v2 = ~v1["ai_attribue"] & v2["ai_attribue"]
    inconsistent = v2["ai_attribue"] & (
        v2["outil"].isna() | v2["type_preuve"].isna() | v2["signal_attribution"].isna()
    )

    failures = []
    if len(source) == 0:
        failures.append("empty_dataset")
    if bool(lost_v1.any()):
        failures.append("v1_detection_lost_in_v2")
    if bool(inconsistent.any()):
        failures.append("incomplete_v2_attribution")

    additions = []
    for index in v2.index[new_v2]:
        additions.append({
            "identifiant": str(v2.at[index, "identifiant"]),
            "outil": str(v2.at[index, "outil"]),
            "type_preuve": str(v2.at[index, "type_preuve"]),
            "signal_attribution": str(v2.at[index, "signal_attribution"]),
            "title": str(v2.at[index, "title"]),
        })

    return {
        "depot": repository,
        "fichier": filename,
        "statut": "reussi" if not failures else "echec",
        "erreurs": failures,
        "prs": int(len(source)),
        "detectees_v1": int(v1["ai_attribue"].sum()),
        "detectees_v2": int(v2["ai_attribue"].sum()),
        "perdues_depuis_v1": int(lost_v1.sum()),
        "nouvelles_v2": int(new_v2.sum()),
        "details_nouvelles_v2": additions,
    }


def main() -> None:
    repositories = [validate_repository(repository, filename) for repository, filename in REPOSITORIES.items()]
    failures = [result["depot"] for result in repositories if result["statut"] != "reussi"]
    report = {
        "detecteur": "v2",
        "nombre_depots_attendu": 8,
        "nombre_depots_testes": len(repositories),
        "statut_global": "reussi" if len(repositories) == 8 and not failures else "echec",
        "prs_testees": sum(result["prs"] for result in repositories),
        "detectees_v1": sum(result["detectees_v1"] for result in repositories),
        "detectees_v2": sum(result["detectees_v2"] for result in repositories),
        "nouvelles_v2": sum(result["nouvelles_v2"] for result in repositories),
        "depots": repositories,
    }
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))
    if report["statut_global"] != "reussi":
        raise SystemExit(1)


if __name__ == "__main__":
    main()