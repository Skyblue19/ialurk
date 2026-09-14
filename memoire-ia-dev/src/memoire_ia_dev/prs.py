"""GitHub pull-request collection and explicit-attribution detection."""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable, Literal

import pandas as pd

from .detection import COMMIT_RULES, Attribution


class GitHubRateLimitError(RuntimeError):
    """Raised when GitHub rejects a request because the API quota is exhausted."""

    def __init__(self, reset_at: int | None = None) -> None:
        self.reset_at = reset_at
        super().__init__("GitHub API rate limit exhausted")

    def wait_seconds(self) -> int:
        if self.reset_at is None:
            return 60
        return max(1, self.reset_at - int(datetime.now(timezone.utc).timestamp()) + 1)


# Anchored login patterns observed in the AIDev corpus on 2026-08-25.
AI_AGENT_LOGIN_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("copilot", re.compile(r"^copilot(\[bot\])?$", re.I)),
    ("claude_code", re.compile(r"^claude(ai-v1|-code)?(\[bot\])?$", re.I)),
    ("devin", re.compile(r"^devin-ai-integration(\[bot\])?$", re.I)),
    ("google_jules", re.compile(r"^google-labs-jules(\[bot\])?$", re.I)),
    ("cursor", re.compile(r"^cursor(agent|-staging)?(\[bot\])?$", re.I)),
    ("codegen", re.compile(r"^codegen-sh(\[bot\])?$", re.I)),
    ("terragon", re.compile(r"^terragon-labs(\[bot\])?$", re.I)),
    ("wildcard", re.compile(r"^wildcard-ai-integration(\[bot\])?$", re.I)),
)

# Branch prefixes created by the agent itself; verified against live GitHub PRs on 2026-08-25.
AGENT_BRANCH_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("codex", re.compile(r"^codex/", re.I)),
    ("cursor", re.compile(r"^cursor/", re.I)),
    ("copilot", re.compile(r"^copilot/", re.I)),
)

# Frozen V1 task links, retained for reproducible before/after comparisons.
AGENT_LINK_RULES_V1: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("codex", re.compile(r"https?://chatgpt\.com/codex", re.I)),
    ("cursor", re.compile(r"https?://cursor\.com/(agents|bc)", re.I)),
)

# V2 task links and explicit declarations measured on the AIDev corpus.
AGENT_LINK_RULES_V2: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("codex", re.compile(
        r"https?://chatgpt\.com/(?:codex(?:[/?#]|$)|s/cd_[a-z0-9]+(?:[/?#]|$)|"
        r"tasks/task_e_[a-z0-9]+(?:[/?#]|$))",
        re.I,
    )),
    ("cursor", re.compile(
        r"https?://(?:www\.)?cursor\.com/(?:agents|bc|background-agent)(?:[/?#]|$)",
        re.I,
    )),
)

AGENT_DECLARATION_RULES_V2: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("cursor", re.compile(
        r"\b(?:generated|created|implemented|written|made)\s+(?:with|by)\s+(?:the\s+)?"
        r"cursor(?:\s+(?:agent|ai|background\s+composer))?\b",
        re.I,
    )),
    ("codex", re.compile(
        r"\b(?:generated|created|implemented|written|made)\s+(?:with|by)\s+"
        r"(?:openai\s+)?codex(?:\s+(?:cli|agent))?\b",
        re.I,
    )),
)

DetectorVersion = Literal["v1", "v2"]

# Automation accounts that are not AI coding agents; excluded to avoid false positives.
NON_AI_AUTOMATION = re.compile(
    r"^(github-actions|dependabot|renovate|codecov|snyk|autofix-ci|pre-commit-ci|mergify|"
    r"stale|allcontributors|imgbot|netlify|vercel|sonarcloud|semantic-release)(\[bot\])?$",
    re.I,
)


def _match_agent_login(login: str) -> str | None:
    for tool, pattern in AI_AGENT_LOGIN_RULES:
        if pattern.search(login):
            return tool
    return None


def detect_pr_attribution(
    record: dict[str, Any] | pd.Series, version: DetectorVersion = "v2"
) -> Attribution | None:
    """Detect PR signals while keeping structural and textual proof separate."""
    if version not in ("v1", "v2"):
        raise ValueError(f"Unsupported detector version: {version}")

    author_login = str(record.get("author_login", "") or "").strip()
    committer_login = str(record.get("committer_login", "") or "").strip()

    if tool := _match_agent_login(author_login):
        return Attribution(tool, "structurelle", "author_login")
    if tool := _match_agent_login(committer_login):
        return Attribution(tool, "structurelle", "committer_login")

    if not NON_AI_AUTOMATION.search(author_login) and (
        record.get("author_type") == "Bot" or bool(record.get("performed_via_github_app"))
    ):
        return Attribution("bot_generique", "structurelle", "github_account_or_app")

    head_ref = str(record.get("head_ref", "") or "").strip()
    for tool, pattern in AGENT_BRANCH_RULES:
        if pattern.search(head_ref):
            return Attribution(tool, "convention_branche", "head_ref")

    text = f"{record.get('title', '') or ''}\n{record.get('body', '') or ''}"
    link_rules = AGENT_LINK_RULES_V1 if version == "v1" else AGENT_LINK_RULES_V2
    for tool, pattern in link_rules:
        if pattern.search(text):
            return Attribution(tool, "auto_declaration", "lien_agent")
    if version == "v2":
        for tool, pattern in AGENT_DECLARATION_RULES_V2:
            if pattern.search(text):
                return Attribution(tool, "auto_declaration", "title_or_body")
    for tool, _, field, pattern in COMMIT_RULES:
        if field == "message" and pattern.search(text):
            return Attribution(tool, "auto_declaration", "title_or_body")
    return None


def tag_prs(prs: pd.DataFrame, version: DetectorVersion = "v2") -> pd.DataFrame:
    """Add observable attribution columns to PR metadata."""
    result = prs.copy()
    detected = result.apply(lambda row: detect_pr_attribution(row, version=version), axis=1)
    result["outil"] = detected.map(lambda item: item.tool if item else None)
    result["type_preuve"] = detected.map(lambda item: item.evidence_type if item else None)
    result["signal_attribution"] = detected.map(lambda item: item.signal if item else None)
    result["bot_generique_detecte"] = result["outil"].eq("bot_generique")
    result["ai_attribue"] = detected.notna() & ~result["bot_generique_detecte"]
    return result


def get_pull_requests(
    owner: str,
    repo: str,
    token: str | None = None,
    since: str | None = None,
    until: str | None = None,
    start_page: int = 1,
    max_pages: int | None = None,
    on_page: Callable[[pd.DataFrame, int], None] | None = None,
    include_commit_identities: bool = False,
) -> tuple[pd.DataFrame, bool, int]:
    """Collect a bounded PR window, optionally emitting each completed page.

    Returns tagged rows, whether the requested window is complete, and the next page.
    """
    try:
        import requests
    except ImportError as error:
        raise RuntimeError("Install collection dependencies with: pip install -e '.[collect]'") from error

    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    since_date = _parse_bound(since)
    until_date = _parse_bound(until)
    if since_date and until_date and since_date > until_date:
        raise ValueError("--since must be earlier than or equal to --until")
    rows: list[dict[str, object]] = []
    page = start_page
    pages_collected = 0
    while True:
        response = _get_with_retries(
            requests,
            f"https://api.github.com/repos/{owner}/{repo}/pulls",
            headers,
            {"state": "closed", "sort": "created", "direction": "desc", "per_page": 100, "page": page},
            ignore_forbidden=True,
            raise_on_rate_limit=True,
        )
        if response is None:
            return tag_commits_or_prs(rows), False, page
        batch = response.json()
        if not batch:
            return tag_commits_or_prs(rows), True, page
        page_rows: list[dict[str, object]] = []
        for pr in batch:
            created_at = pd.to_datetime(pr.get("created_at"), utc=True)
            if until_date and created_at > until_date:
                continue
            if since_date and created_at < since_date:
                continue
            user = pr.get("user") or {}
            page_rows.append({
                "identifiant": str(pr["number"]), "author_login": user.get("login"),
                "committer_login": None,
                "author_type": user.get("type"),
                "head_ref": (pr.get("head") or {}).get("ref"),
                "performed_via_github_app": pr.get("performed_via_github_app") is not None,
                "title": pr.get("title", ""), "body": pr.get("body") or "",
                "labels": [label["name"] for label in pr.get("labels", [])],
                "created_at": pr.get("created_at"), "merged_at": pr.get("merged_at"),
                "closed_at": pr.get("closed_at"), "merge_commit_sha": pr.get("merge_commit_sha"),
            })
        tagged_page = tag_prs(pd.DataFrame(page_rows, columns=[
            "identifiant", "author_login", "committer_login", "author_type", "head_ref",
            "performed_via_github_app", "title", "body", "labels", "created_at", "merged_at",
            "closed_at", "merge_commit_sha",
        ]))
        if include_commit_identities:
            candidates = tagged_page.index[tagged_page["outil"].isna()]
            with ThreadPoolExecutor(max_workers=3) as executor:
                lookups = executor.map(
                    lambda index: _find_agent_committer_login(
                        requests, owner, repo, str(tagged_page.at[index, "identifiant"]), headers
                    ),
                    candidates,
                )
            for index, committer_login in zip(candidates, lookups):
                if committer_login:
                    tagged_page.at[index, "committer_login"] = committer_login
            tagged_page = tag_prs(tagged_page)
        rows.extend(tagged_page.to_dict("records"))
        page += 1
        pages_collected += 1
        if on_page:
            on_page(tagged_page, page)
        oldest_created_at = pd.to_datetime(batch[-1].get("created_at"), utc=True)
        if since_date and oldest_created_at < since_date:
            return tag_commits_or_prs(rows), True, page
        if max_pages and pages_collected >= max_pages:
            return tag_commits_or_prs(rows), False, page
    return tag_commits_or_prs(rows), True, page

def get_pull_request_total(owner: str, repo: str, token: str | None, since: str, until: str) -> int:
    """Return GitHub's count of closed pull requests created in the date window."""
    try:
        import requests
    except ImportError as error:
        raise RuntimeError("Install collection dependencies with: pip install -e '.[collect]'") from error

    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.get(
        "https://api.github.com/search/issues",
        headers=headers,
        params={"q": f"repo:{owner}/{repo} is:pr is:closed created:{since}..{until}", "per_page": 1},
        timeout=30,
    )
    response_headers = getattr(response, "headers", {})
    if response.status_code == 403 and response_headers.get("x-ratelimit-remaining") == "0":
        reset = response_headers.get("x-ratelimit-reset")
        raise GitHubRateLimitError(int(reset)) if reset and reset.isdigit() else GitHubRateLimitError()
    response.raise_for_status()
    return int(response.json()["total_count"])


def _parse_bound(value: str | None) -> datetime | None:
    if value is None:
        return None
    return pd.to_datetime(value, utc=True).to_pydatetime()


def _find_agent_committer_login(
    requests: Any, owner: str, repo: str, pull_number: str, headers: dict[str, str]
) -> str | None:
    """Return a recognized agent committer from one otherwise unattributed PR."""
    page = 1
    while True:
        response = _get_with_retries(
            requests,
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}/commits",
            headers,
            {"per_page": 100, "page": page},
            ignore_forbidden=True,
        )
        if response is None:
            return None
        commits = response.json()
        for commit in commits:
            login = str((commit.get("committer") or {}).get("login") or "").strip()
            if _match_agent_login(login):
                return login
        if len(commits) < 100:
            return None
        page += 1


def _get_with_retries(
    requests: Any,
    url: str,
    headers: dict[str, str],
    params: dict[str, object],
    ignore_forbidden: bool = False,
    raise_on_rate_limit: bool = False,
) -> Any | None:
    """Retry transient server and connection failures without hiding client errors."""
    for attempt in range(3):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response_headers = getattr(response, "headers", {})
            if response.status_code == 403 and raise_on_rate_limit:
                reset = response_headers.get("x-ratelimit-reset")
                raise GitHubRateLimitError(int(reset)) if reset and reset.isdigit() else GitHubRateLimitError()
            if response.status_code == 403 and ignore_forbidden:
                return None
            if response.status_code >= 500:
                if attempt < 2:
                    time.sleep(1 << attempt)
                    continue
                return None
            response.raise_for_status()
            return response
        except GitHubRateLimitError:
            raise
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            if attempt < 2:
                time.sleep(1 << attempt)
                continue
            return None
    return None


def tag_commits_or_prs(rows: list[dict[str, object]]) -> pd.DataFrame:
    """Return a stable empty result when no PR falls inside the requested window."""
    if not rows:
        return pd.DataFrame(columns=["identifiant", "ai_attribue", "outil", "type_preuve", "signal_attribution"])
    return pd.DataFrame(rows)