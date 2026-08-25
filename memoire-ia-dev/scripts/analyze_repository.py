"""Generate quarterly repository analysis tables and charts from raw exports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from memoire_ia_dev.metrics import add_year_and_period, build_quarterly_summary


SUMMARY_COLUMNS = ["annee_trimestre", "depot", "ai_attribue", "outil", "type_preuve"]


def load_channel(path: Path | None, date_column: str, repository: str, start: str | None, end: str | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)
    frame = pd.read_csv(path)
    if frame.empty:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)
    frame = add_year_and_period(frame, date_column)
    if start:
        frame = frame.loc[frame[date_column] >= pd.Timestamp(start, tz="UTC")]
    if end:
        frame = frame.loc[frame[date_column] <= pd.Timestamp(end, tz="UTC")]
    frame["depot"] = repository
    return frame


def plot_channel(summary: pd.DataFrame, total_column: str, attributed_column: str, title: str, output: Path) -> None:
    figure, axis = plt.subplots(figsize=(10, 5))
    if summary.empty or summary[total_column].sum() == 0:
        axis.text(0.5, 0.5, "No data in the requested window", ha="center", va="center")
        axis.set_axis_off()
    else:
        axis.plot(summary["annee_trimestre"], summary[total_column], marker="o", label="Total")
        axis.plot(summary["annee_trimestre"], summary[attributed_column], marker="o", label="Explicit AI attribution")
        axis.set_ylabel("Count")
        axis.legend()
        axis.tick_params(axis="x", rotation=45)
        axis.grid(axis="y", alpha=0.3)
    axis.set_title(title)
    figure.tight_layout()
    figure.savefig(output, dpi=180)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build quarterly analysis tables and charts for one repository.")
    parser.add_argument("--repo", required=True, help="Repository identifier, for example ppy/osu.")
    parser.add_argument("--commits", type=Path, help="Raw commit CSV from the commits command.")
    parser.add_argument("--prs", type=Path, help="Raw PR CSV from the prs command.")
    parser.add_argument("--start", help="Inclusive UTC date, for example 2020-06-01.")
    parser.add_argument("--end", help="Inclusive UTC date, for example 2026-08-25.")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    commits = load_channel(args.commits, "date", args.repo, args.start, args.end)
    prs = load_channel(args.prs, "created_at", args.repo, args.start, args.end)
    summary = build_quarterly_summary(commits, prs)
    prefix = args.repo.replace("/", "_")
    summary.to_csv(args.output_dir / f"{prefix}_quarterly_summary.csv", index=False)
    plot_channel(summary, "nb_commits", "nb_commits_ia", f"{args.repo}: commits by quarter", args.output_dir / f"{prefix}_commits_quarterly.png")
    plot_channel(summary, "nb_prs", "nb_prs_ia", f"{args.repo}: pull requests by quarter", args.output_dir / f"{prefix}_prs_quarterly.png")

    report = {
        "repo": args.repo,
        "start": args.start,
        "end": args.end,
        "quarters": int(len(summary)),
        "commits": int(len(commits)),
        "commits_attributed": int(commits["ai_attribue"].sum()) if not commits.empty else 0,
        "pull_requests": int(len(prs)),
        "pull_requests_attributed": int(prs["ai_attribue"].sum()) if not prs.empty else 0,
    }
    (args.output_dir / f"{prefix}_analysis_report.json").write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
