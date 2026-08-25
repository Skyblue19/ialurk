"""Known configuration-file signals and reproducible repository manifests."""

from __future__ import annotations

import csv
from pathlib import Path


CONFIG_FILES: dict[str, tuple[str, ...]] = {
    "claude_code": ("CLAUDE.md", ".claude/"),
    "copilot": ("copilot-instructions.md", ".github/copilot-instructions.md"),
    "cursor": (".cursorrules", ".cursor/rules/"),
    "aider": (".aider.conf.yml",),
    "replit": (".replit",),
    "codex": ("AGENTS.md",),
    "devin": (".devin.yaml",),
}


def load_repositories(path: str | Path) -> list[dict[str, str]]:
    """Load the documented sample from a CSV manifest."""
    with Path(path).open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))