"""Known configuration-file signals and reproducible repository manifests."""

from __future__ import annotations

import csv
import re
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

REJECTION_MARKERS = re.compile(
    r"\b(?:do not review|do not request|decline|discouraged?|not to request|opt[- ]?out|disable[sd]?)\b",
    re.I,
)


def classify_config_file_content(content: str) -> str:
    """Classify a configuration file using explicit rejection language only."""
    return "rejet" if REJECTION_MARKERS.search(content) else "adoption"


def load_repositories(path: str | Path) -> list[dict[str, str]]:
    """Load the documented sample from a CSV manifest."""
    with Path(path).open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))