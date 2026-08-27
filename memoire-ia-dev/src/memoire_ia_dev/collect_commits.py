"""Git-history extraction and configuration-based internal bascules."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import subprocess

import pandas as pd

from .config import CONFIG_FILES, classify_config_file_content
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
        result = result.loc[result["date"] >= pd.to_datetime(since, utc=True)]
    if to:
        result = result.loc[result["date"] <= pd.to_datetime(to, utc=True)]
    return tag_commits(result)


def find_config_bascule_details(repo_path: str | Path) -> pd.DataFrame:
    """Inspect added configuration content and retain adoption/rejection status."""
    rows: list[dict[str, str]] = []
    for tool, paths in CONFIG_FILES.items():
        for config_path in paths:
            completed = subprocess.run(
                ["git", "-C", str(repo_path), "log", "--diff-filter=A", "--format=%H%x1f%aI", "--", config_path],
                capture_output=True,
                text=True,
                check=True,
            )
            for line in completed.stdout.splitlines():
                if not line:
                    continue
                commit, date = line.split("\x1f", maxsplit=1)
                content = _config_content_at_revision(repo_path, commit, config_path)
                rows.append({
                    "outil": tool, "chemin": config_path, "commit": commit, "date_bascule": date,
                    "statut_config": classify_config_file_content(content),
                })
    if not rows:
        return pd.DataFrame(columns=["outil", "chemin", "commit", "date_bascule", "statut_config"])
    return pd.DataFrame(rows).sort_values("date_bascule").drop_duplicates("outil", keep="first").reset_index(drop=True)


def _config_content_at_revision(repo_path: str | Path, commit: str, config_path: str) -> str:
    """Read a tracked config file at its addition revision; directories have no blob."""
    if config_path.endswith("/"):
        listed = subprocess.run(
            ["git", "-C", str(repo_path), "diff-tree", "--no-commit-id", "--name-only", "-r", commit],
            capture_output=True, text=True, check=True,
        )
        paths = [path for path in listed.stdout.splitlines() if path.startswith(config_path)]
        return "\n".join(_config_content_at_revision(repo_path, commit, path) for path in paths)
    shown = subprocess.run(
        ["git", "-C", str(repo_path), "show", f"{commit}:{config_path}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return shown.stdout if shown.returncode == 0 else ""


def find_config_bascules(repo_path: str | Path) -> dict[str, str]:
    """Return earliest adoption dates; explicit rejections are not adoption bascules."""
    details = find_config_bascule_details(repo_path)
    adopted = details.loc[details["statut_config"].eq("adoption")]
    return dict(zip(adopted["outil"], adopted["date_bascule"]))