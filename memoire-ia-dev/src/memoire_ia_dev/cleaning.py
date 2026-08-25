"""Auditable cleaning and task categorization for extracted commit metadata."""

from __future__ import annotations

import re

import pandas as pd


AUTOMATION_ACCOUNT = re.compile(r"dependabot|renovate|github-actions|github-action|codecov|snyk", re.I)
TASK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("fix", re.compile(r"\bfix(e[sd])?|bug|correct|repair\b", re.I)),
    ("feat", re.compile(r"\bfeat(ure)?|add(ed|s|ing)?|implement\b", re.I)),
    ("refactor", re.compile(r"\brefactor|cleanup|restructur\b", re.I)),
    ("docs", re.compile(r"\bdocs?|readme|documentation\b", re.I)),
    ("test", re.compile(r"\btests?|spec\b", re.I)),
)


def classify_task(message: str) -> str:
    """Classify a commit message using documented deterministic keyword rules."""
    for category, pattern in TASK_PATTERNS:
        if pattern.search(message or ""):
            return category
    return "other"


def clean_commits(commits: pd.DataFrame, outlier_size: int = 50_000) -> pd.DataFrame:
    """Flag automation and extreme sizes; retain all rows for transparent sensitivity analysis."""
    result = commits.copy()
    account = result.get("author_name", pd.Series("", index=result.index)).fillna("") + " " + result.get("author_email", pd.Series("", index=result.index)).fillna("")
    result["bot_automation"] = account.str.contains(AUTOMATION_ACCOUNT)
    result["taille"] = result["lines_added"].fillna(0) + result["lines_deleted"].fillna(0)
    result["taille_aberrante"] = result["taille"].gt(outlier_size)
    result["categorie_tache"] = result["message"].fillna("").map(classify_task)
    return result