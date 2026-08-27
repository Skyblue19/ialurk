"""Batch collection and analysis workflow driven by the repository manifest."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Callable

import pandas as pd

from .collect_commits import extract_commits_fast, find_config_bascule_details
from .config import load_repositories
from .prs import GitHubRateLimitError, get_pull_requests
from .prs import get_pull_request_total


def run_batch(
    manifest: str | Path,
    workdir: str | Path,
    rawdir: str | Path,
    processeddir: str | Path,
    since: str,
    until: str,
    commit_identities: bool = True,
    max_pages: int = 50,
    wait_for_rate_limit: bool = False,
    progress: Callable[[str], None] = print,
) -> None:
    """Run the complete workflow for every manifest row with resumable PR chunks."""
    repositories = load_repositories(manifest)
    total = len(repositories)
    for index, repository in enumerate(repositories, start=1):
        name = repository["depot"]
        owner, repo = name.split("/", maxsplit=1)
        prefix = name.replace("/", "_")
        repo_path = Path(workdir) / prefix
        raw_path = Path(rawdir)
        processed_path = Path(processeddir) / prefix
        repo_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.mkdir(parents=True, exist_ok=True)
        processed_path.mkdir(parents=True, exist_ok=True)
        if _is_repository_complete(processed_path, name, since, until, commit_identities):
            _report(progress, index, total, name, "termine")
            continue
        _report(progress, index, total, name, "clone")
        _ensure_clone(repository["url"], repo_path)

        _report(progress, index, total, name, "bascules")
        find_config_bascule_details(repo_path).to_csv(raw_path / f"{prefix}_config_bascule_details.csv", index=False)

        _report(progress, index, total, name, "commits")
        extract_commits_fast(repo_path, _parse_date(since), _parse_date(until)).to_csv(raw_path / f"{prefix}_commits.csv", index=False)

        _report(progress, index, total, name, "prs")
        while True:
            checkpoint = raw_path / f"{prefix}_prs.checkpoint.json"
            previous_page = int(json.loads(checkpoint.read_text(encoding="utf-8")).get("next_page", 1)) if checkpoint.exists() else 1
            try:
                complete = _collect_prs(
                    owner, repo, raw_path / f"{prefix}_prs.csv", since, until,
                    os.getenv("GITHUB_TOKEN"), commit_identities, max_pages, progress, index, total, name,
                )
            except GitHubRateLimitError as error:
                if not wait_for_rate_limit:
                    progress(f"[{index}/{total}] {name} | collecte PR suspendue par GitHub, relancer le batch plus tard")
                    return
                wait_seconds = error.wait_seconds()
                progress(f"[{index}/{total}] {name} | quota GitHub epuise, reprise automatique dans {wait_seconds}s")
                time.sleep(wait_seconds)
                continue
            if complete:
                break
            next_page = int(json.loads(checkpoint.read_text(encoding="utf-8")).get("next_page", previous_page))
            if next_page == previous_page:
                progress(f"[{index}/{total}] {name} | collecte PR suspendue par GitHub, relancer le batch plus tard")
                return
            progress(f"[{index}/{total}] {name} | checkpoint conserve, prochaine tranche PR")

        _report(progress, index, total, name, "analyse")
        subprocess.run([
            sys.executable, "scripts/analyze_repository.py", "--repo", name,
            "--commits", str(raw_path / f"{prefix}_commits.csv"),
            "--prs", str(raw_path / f"{prefix}_prs.csv"), "--start", since, "--end", until,
            "--output-dir", str(processed_path),
        ], check=True)
        _completion_marker(processed_path).write_text(json.dumps({
            "repo": name, "since": since, "until": until,
            "commit_identities": commit_identities,
        }, ensure_ascii=True, indent=2), encoding="utf-8")
        _report(progress, index, total, name, "termine")


def _collect_prs(owner, repo, output, since, until, token, commit_identities, max_pages, progress, index, total, name) -> bool:
    checkpoint = output.with_suffix(".checkpoint.json")
    existing_ids = set(pd.read_csv(output, usecols=["identifiant"], dtype=str)["identifiant"]) if output.exists() else set()
    existing_count = len(existing_ids)
    state = json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.exists() else {}
    if state and (state.get("owner"), state.get("repo"), state.get("since"), state.get("until"), state.get("commit_identities")) != (owner, repo, since, until, commit_identities):
        raise ValueError(f"Checkpoint incompatible avec {name}")
    start_page = int(state.get("next_page", 1))
    expected_total = state.get("expected_total")
    if expected_total is None:
        expected_total = get_pull_request_total(owner, repo, token, since, until)

    def save_page(page_frame, next_page):
        nonlocal existing_count
        page_frame = page_frame.loc[~page_frame["identifiant"].astype(str).isin(existing_ids)].copy()
        if not page_frame.empty:
            page_frame.to_csv(output, mode="a", header=not output.exists(), index=False)
            existing_ids.update(page_frame["identifiant"].astype(str))
            existing_count += len(page_frame)
        checkpoint.write_text(json.dumps({
            "owner": owner, "repo": repo, "since": since, "until": until,
            "commit_identities": commit_identities, "next_page": next_page, "expected_total": expected_total,
        }, ensure_ascii=True, indent=2), encoding="utf-8")
        percent = min(100, int(existing_count / expected_total * 100)) if expected_total else 100
        progress(f"[{index}/{total}] {name} | PR page {next_page - 1} | progression PR {percent}% | {existing_count}/{expected_total} PR")

    _, complete, _ = get_pull_requests(
        owner, repo, token, since, until, start_page, max_pages, save_page, include_commit_identities=commit_identities,
    )
    if complete:
        checkpoint.unlink(missing_ok=True)
    return complete


def _completion_marker(processed_path: Path) -> Path:
    return processed_path / ".batch-complete.json"


def _is_repository_complete(
    processed_path: Path, name: str, since: str, until: str, commit_identities: bool,
) -> bool:
    marker = _completion_marker(processed_path)
    if marker.exists():
        state = json.loads(marker.read_text(encoding="utf-8"))
        return (state.get("repo"), state.get("since"), state.get("until"), state.get("commit_identities")) == (
            name, since, until, commit_identities,
        )

    report = processed_path / f"{name.replace('/', '_')}_analysis_report.json"
    if not report.exists():
        return False
    state = json.loads(report.read_text(encoding="utf-8"))
    if (state.get("repo"), state.get("start"), state.get("end")) != (name, since, until):
        return False
    marker.write_text(json.dumps({
        "repo": name, "since": since, "until": until,
        "commit_identities": commit_identities,
    }, ensure_ascii=True, indent=2), encoding="utf-8")
    return True


def _ensure_clone(url: str, destination: Path) -> None:
    if (destination / ".git").exists():
        subprocess.run(["git", "-C", str(destination), "fetch", "--all", "--prune"], check=True)
        return
    if destination.exists() and any(destination.iterdir()):
        raise ValueError(f"Le dossier de clone n'est pas vide: {destination}")
    subprocess.run(["git", "clone", url, str(destination)], check=True)


def _parse_date(value: str):
    return pd.to_datetime(value, utc=True).to_pydatetime()


def _report(progress, index: int, total: int, name: str, stage: str) -> None:
    percent = int(((index - 1) * 5 + {"clone": 0, "bascules": 1, "commits": 2, "prs": 3, "analyse": 4, "termine": 5}[stage]) / (total * 5) * 100)
    progress(f"[{percent:3d}%] depot {index}/{total}: {name} | {stage}")