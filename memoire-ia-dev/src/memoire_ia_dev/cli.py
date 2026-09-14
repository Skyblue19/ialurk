"""Small command-line interface for the reproducible collection workflow."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path

import pandas as pd

from .collect_commits import extract_commits, extract_commits_fast, find_config_bascule_details, find_config_bascules
from .batch import run_batch
from .prs import get_pull_requests
from .validation import evaluate_aidev_full, load_aidev

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure explicit AI attributions in repository metadata.")
    commands = parser.add_subparsers(dest="command", required=True)
    commit_parser = commands.add_parser("commits", help="Extract and tag commits from a local clone.")
    commit_parser.add_argument("repo_path")
    commit_parser.add_argument("output")
    commit_parser.add_argument("--since", help="Inclusive commit author date, for example 2023-01-01.")
    commit_parser.add_argument("--until", help="Inclusive commit author date, for example 2025-12-31.")
    commit_parser.add_argument("--fast", action="store_true", help="Use git metadata only; omit diff-size metrics for large histories.")
    bascule_parser = commands.add_parser("bascules", help="Find configuration-file bascules in a local clone.")
    bascule_parser.add_argument("repo_path")
    bascule_parser.add_argument("--details", action="store_true", help="Include rejected configuration files and their addition commits.")
    pr_parser = commands.add_parser("prs", help="Collect and tag closed GitHub pull requests.")
    pr_parser.add_argument("owner")
    pr_parser.add_argument("repo")
    pr_parser.add_argument("output")
    pr_parser.add_argument("--since", help="Inclusive PR creation date, for example 2023-01-01.")
    pr_parser.add_argument("--until", help="Inclusive PR creation date, for example 2025-12-31.")
    pr_parser.add_argument("--max-pages", type=int, help="Stop after this many API pages; use --resume to continue.")
    pr_parser.add_argument(
        "--commit-identities", action="store_true",
        help="For PRs without another signal, inspect committers for recognized AI agent accounts (uses extra API requests).",
    )
    pr_parser.add_argument("--resume", action="store_true", help="Continue from the checkpoint next to the output CSV.")
    status_parser = commands.add_parser("status", help="Show collection coverage and checkpoint progress for a PR CSV.")
    status_parser.add_argument("output", help="PR CSV path used by the prs command")
    status_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    aidev_parser = commands.add_parser("eval-aidev", help="Evaluate PR detection over the complete AIDev positive corpus.")
    aidev_parser.add_argument("output", help="JSON report path")
    aidev_parser.add_argument("--records-output", help="Optional CSV path for row-level evaluation records")
    aidev_parser.add_argument("--detector-version", choices=("v1", "v2"), default="v2")
    aidev_parser.add_argument("--comparison-output", help="Optional JSON report comparing V1 and V2")
    batch_parser = commands.add_parser("batch", help="Run the manifest-driven collection and analysis workflow.")
    batch_parser.add_argument("manifest", help="CSV repository manifest")
    batch_parser.add_argument("--workdir", default=".work", help="Directory for local clones")
    batch_parser.add_argument("--rawdir", default="data/raw", help="Directory for raw CSV exports")
    batch_parser.add_argument("--processeddir", default="data/processed", help="Directory for summaries and charts")
    batch_parser.add_argument("--since", default="2020-06-01")
    batch_parser.add_argument("--until", default="2026-08-25")
    batch_parser.add_argument("--max-pages", type=int, default=50, help="PR pages per resumable batch")
    batch_parser.add_argument("--no-commit-identities", action="store_true", help="Disable targeted committer identity lookups")
    batch_parser.add_argument("--wait-for-rate-limit", action="store_true", help="Wait for GitHub quota reset and resume automatically")
    args = parser.parse_args()

    if args.command == "commits":
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        extractor = extract_commits_fast if args.fast else extract_commits
        extractor(args.repo_path, _parse_date(args.since), _parse_date(args.until)).to_csv(output, index=False)
    elif args.command == "bascules":
        if args.details:
            print(find_config_bascule_details(args.repo_path).to_csv(index=False), end="")
        else:
            for tool, date in find_config_bascules(args.repo_path).items():
                print(f"{tool},{date}")
    elif args.command == "prs":
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        if load_dotenv:
            load_dotenv(override=True)
        checkpoint = output.with_suffix(".checkpoint.json")
        start_page = 1
        existing = pd.DataFrame()
        if args.resume:
            if not checkpoint.exists():
                raise FileNotFoundError(f"No checkpoint found: {checkpoint}")
            state = json.loads(checkpoint.read_text(encoding="utf-8"))
            if state["owner"] != args.owner or state["repo"] != args.repo:
                raise ValueError("Checkpoint repository does not match the requested repository")
            if state.get("since") != args.since or state.get("until") != args.until:
                raise ValueError("Checkpoint dates do not match the requested period")
            if state.get("commit_identities", False) != args.commit_identities:
                raise ValueError("Checkpoint commit identity setting does not match the requested collection")
            start_page = state["next_page"]
            if output.exists():
                existing = pd.read_csv(output)

        def save_page(page_frame, next_page):
            nonlocal existing
            existing = pd.concat([existing, page_frame], ignore_index=True).drop_duplicates("identifiant", keep="first")
            existing.to_csv(output, index=False)
            checkpoint.write_text(json.dumps({
                "owner": args.owner, "repo": args.repo, "since": args.since,
                "until": args.until, "commit_identities": args.commit_identities, "next_page": next_page,
            }, ensure_ascii=True, indent=2), encoding="utf-8")

        _, complete, _ = get_pull_requests(
            args.owner, args.repo, os.getenv("GITHUB_TOKEN"), args.since, args.until,
            start_page, args.max_pages, save_page, args.commit_identities,
        )
        if complete:
            checkpoint.unlink(missing_ok=True)
    elif args.command == "status":
        report = collection_status(Path(args.output))
        if args.json:
            print(json.dumps(report, ensure_ascii=True, indent=2))
        else:
            print(f"CSV: {report['csv']}")
            print(f"State: {report['state']}")
            print(f"PR rows: {report['pull_requests']}")
            print(f"Date coverage: {report['earliest_created_at']} -> {report['latest_created_at']}")
            print(f"Explicit AI attributions: {report['ai_attributions']}")
            if report["state"] == "in_progress":
                print(f"Next GitHub page: {report['next_page']}")
                print(f"Window: {report['since']} -> {report['until']}")
    elif args.command == "eval-aidev":
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        reference = load_aidev()
        commits = load_aidev("pr_commits")
        report, records = evaluate_aidev_full(reference, commits, args.detector_version)
        output.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
        if args.records_output:
            records_output = Path(args.records_output)
            records_output.parent.mkdir(parents=True, exist_ok=True)
            records.to_csv(records_output, index=False)
        if args.comparison_output:
            comparison_output = Path(args.comparison_output)
            comparison_output.parent.mkdir(parents=True, exist_ok=True)
            other_version = "v1" if args.detector_version == "v2" else "v2"
            other_report, _ = evaluate_aidev_full(reference, commits, other_version)
            comparison = {args.detector_version: report, other_version: other_report}
            comparison_output.write_text(
                json.dumps(comparison, ensure_ascii=True, indent=2), encoding="utf-8",
            )
        print(json.dumps(report, ensure_ascii=True, indent=2))
    elif args.command == "batch":
        if load_dotenv:
            load_dotenv(override=True)
        run_batch(
            args.manifest, args.workdir, args.rawdir, args.processeddir, args.since, args.until,
            commit_identities=not args.no_commit_identities, max_pages=args.max_pages,
            wait_for_rate_limit=args.wait_for_rate_limit,
        )


def _parse_date(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def collection_status(output: Path) -> dict[str, object]:
    """Summarize a PR collection without contacting GitHub."""
    checkpoint = output.with_suffix(".checkpoint.json")
    frame = pd.read_csv(output) if output.exists() else pd.DataFrame()
    dates = pd.to_datetime(frame["created_at"], utc=True) if "created_at" in frame else pd.Series(dtype="datetime64[ns, UTC]")
    report: dict[str, object] = {
        "csv": str(output),
        "state": "in_progress" if checkpoint.exists() else ("complete" if output.exists() else "not_started"),
        "pull_requests": int(len(frame)),
        "earliest_created_at": dates.min().isoformat() if not dates.empty else None,
        "latest_created_at": dates.max().isoformat() if not dates.empty else None,
        "ai_attributions": int(frame["ai_attribue"].fillna(False).sum()) if "ai_attribue" in frame else 0,
    }
    if checkpoint.exists():
        report.update(json.loads(checkpoint.read_text(encoding="utf-8")))
    return report
