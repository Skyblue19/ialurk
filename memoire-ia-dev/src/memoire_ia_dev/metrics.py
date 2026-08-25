"""Reproducible annual and before/after process metrics."""

from __future__ import annotations

import pandas as pd


def add_year_and_period(frame: pd.DataFrame, date_column: str, bascule: str | None = None) -> pd.DataFrame:
    result = frame.copy()
    result[date_column] = pd.to_datetime(result[date_column], utc=True)
    result["annee"] = result[date_column].dt.year
    result["annee_trimestre"] = result[date_column].dt.tz_localize(None).dt.to_period("Q").astype(str)
    if bascule:
        threshold = pd.to_datetime(bascule, utc=True)
        result["periode"] = result[date_column].ge(threshold).map({True: "apres", False: "avant"})
    return result


def build_annual_summary(commits: pd.DataFrame, prs: pd.DataFrame) -> pd.DataFrame:
    """Build separate annual counts for commit and PR attribution channels."""
    return _build_summary(commits, prs, "annee")


def build_quarterly_summary(commits: pd.DataFrame, prs: pd.DataFrame) -> pd.DataFrame:
    """Build separate quarterly counts for commit and PR attribution channels."""
    return _build_summary(commits, prs, "annee_trimestre")


def _build_summary(commits: pd.DataFrame, prs: pd.DataFrame, period_column: str) -> pd.DataFrame:
    periods = sorted(
        set(commits.get(period_column, pd.Series(dtype=str)))
        | set(prs.get(period_column, pd.Series(dtype=str)))
    )
    rows: list[dict[str, object]] = []
    for period in periods:
        commit_period = commits.loc[commits[period_column] == period]
        pr_period = prs.loc[prs[period_column] == period]
        repositories = set(commit_period.get("depot", pd.Series(dtype=str))) | set(pr_period.get("depot", pd.Series(dtype=str)))
        attributed_repositories = set(commit_period.loc[commit_period["ai_attribue"], "depot"]) | set(pr_period.loc[pr_period["ai_attribue"], "depot"])
        rows.append({
            period_column: period, "nb_depots": len(repositories), "nb_depots_concernes": len(attributed_repositories),
            "pct_depots_concernes": len(attributed_repositories) / len(repositories) if repositories else None,
            "nb_commits": len(commit_period), "nb_commits_ia": int(commit_period["ai_attribue"].sum()),
            "pct_commits_ia": commit_period["ai_attribue"].mean() if len(commit_period) else None,
            "nb_prs": len(pr_period), "nb_prs_ia": int(pr_period["ai_attribue"].sum()),
            "pct_prs_ia": pr_period["ai_attribue"].mean() if len(pr_period) else None,
            "repartition_outil_commits": commit_period.loc[commit_period["ai_attribue"], "outil"].value_counts().to_dict(),
            "repartition_outil_prs": pr_period.loc[pr_period["ai_attribue"], "outil"].value_counts().to_dict(),
            "repartition_preuve_commits": commit_period.loc[commit_period["ai_attribue"], "type_preuve"].value_counts().to_dict(),
            "repartition_preuve_prs": pr_period.loc[pr_period["ai_attribue"], "type_preuve"].value_counts().to_dict(),
        })
    return pd.DataFrame(rows)


def commit_metrics(commits: pd.DataFrame) -> pd.DataFrame:
    """Compute the protocol's initial commit count and median-size metrics."""
    frame = commits.loc[~commits["is_merge"].fillna(False)].copy()
    frame["taille"] = frame["lines_added"].fillna(0) + frame["lines_deleted"].fillna(0)
    return frame.groupby("periode", dropna=False).agg(
        nb_commits=("identifiant", "count"),
        taille_mediane=("taille", "median"),
    ).reset_index()