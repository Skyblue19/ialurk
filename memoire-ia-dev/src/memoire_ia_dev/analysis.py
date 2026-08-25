"""Non-parametric before/after comparisons used in the experimental protocol."""

from __future__ import annotations

from typing import Any

import pandas as pd


def compare_periods(frame: pd.DataFrame, value_column: str) -> dict[str, Any]:
    """Run Mann-Whitney U and report a rank-biserial effect size.

    Returns missing statistics when either period has no usable observation.
    """
    try:
        from scipy.stats import mannwhitneyu
    except ImportError as error:
        raise RuntimeError("Install analysis dependencies with: pip install -e '.[analysis]'") from error

    before = frame.loc[frame["periode"] == "avant", value_column].dropna()
    after = frame.loc[frame["periode"] == "apres", value_column].dropna()
    if before.empty or after.empty:
        return {"statistique_u": None, "p_value": None, "effet_rang_biseriel": None, "n_avant": len(before), "n_apres": len(after)}
    statistic, p_value = mannwhitneyu(before, after, alternative="two-sided")
    effect = (2 * statistic / (len(before) * len(after))) - 1
    return {
        "statistique_u": float(statistic), "p_value": float(p_value), "effet_rang_biseriel": float(effect),
        "n_avant": len(before), "n_apres": len(after),
        "mediane_avant": float(before.median()), "mediane_apres": float(after.median()),
    }