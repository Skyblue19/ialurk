"""Git-history extraction and configuration-based internal bascules."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import subprocess

import pandas as pd

from .config import CONFIG_FILES
from .detection import tag_commits


def extract_commits(repo_path: str | Path, since: datetime | None = None, to: datetime | None = None) -> pd.DataFrame:
    """Extract commit metadata locally; a repository must already be cloned."""
    try:
        from pydriller import Repository
    except ImportError as error:
        raise RuntimeError("Install collection dependencies with: pip install -e '.[collect]'") from error

    rows: list[dict[str, object]] = []
    for commit in Repository(str(repo_path), since=since, to=to).traverse_commits():
        rows.append({
            "identifiant": commit.hash,
            "author_name": commit.author.name,
            "author_email": commit.author.email,
            "date": commit.author_date,
            "message": commit.msg,
            "lines_added": commit.insertions,
            "lines_deleted": commit.deletions,
            "files_changed": commit.files,
            "is_merge": commit.merge,
        })
    return tag_commits(pd.DataFrame(rows))


def extract_commits_fast(repo_path: str | Path, since: datetime | None = None, to: datetime | None = None) -> pd.DataFrame:
    """Extract Git metadata without diff parsing, for large time-series collection."""
    command = ["git", "-C", str(repo_path), "log", "--format=%H%x1f%an%x1f%ae%x1f%aI%x1f%P%x1f%B%x1e"]
    if since:
        command.append(f"--since={since.isoformat()}")
    if to:
        command.append(f"--until={to.isoformat()}")
    completed = subprocess.run(command, capture_output=True, text=True, check=True, encoding="utf-8", errors="replace")
    rows: list[dict[str, object]] = []
    for record in completed.stdout.split("\x1e"):
        fields = record.strip().split("\x1f", maxsplit=5)
        if len(fields) != 6:
            continue
        commit_hash, author_name, author_email, date, parents, message = fields
        rows.append({
            "identifiant": commit_hash,
            "author_name": author_name,
            "author_email": author_email,
            "date": date,
            "message": message,
            "lines_added": None,
            "lines_deleted": None,
            "files_changed": None,
            "is_merge": len(parents.split()) > 1,
        })
    result = pd.DataFrame(rows)
    if result.empty:
        return tag_commits(result)
    result["date"] = pd.to_datetime(result["date"], utc=True)
    if since:
        result = result.loc[result["date"] >= pd.Timestamp(since, tz="UTC")]
    if to:
        result = result.loc[result["date"] <= pd.Timestamp(to, tz="UTC")]
    return tag_commits(result)


def find_config_bascules(repo_path: str | Path) -> dict[str, str]:
    """Find the earliest commit that added each known AI-tool configuration file."""
    results: dict[str, str] = {}
    for tool, paths in CONFIG_FILES.items():
        dates: list[str] = []
        for config_path in paths:
            completed = subprocess.run(
                ["git", "-C", str(repo_path), "log", "--diff-filter=A", "--format=%aI", "--", config_path],
                capture_output=True,
                text=True,
                check=True,
            )
            dates.extend(line for line in completed.stdout.splitlines() if line)
        if dates:
            results[tool] = min(dates)
    return results