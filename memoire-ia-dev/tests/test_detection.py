import pandas as pd

from memoire_ia_dev.detection import detect_commit_attribution, tag_commits


def test_detects_explicit_claude_code_signals() -> None:
    messages = (
        "Co-Authored-By: Claude <noreply@anthropic.com>",
        "Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>",
        "Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>",
        "Co-Authored-By: Claude Code (kimi-k3[1m]) <noreply@anthropic.com>",
        "Co-Authored-By: Claude [noreply@anthropic.com](mailto:noreply@anthropic.com)",
        "Co-Authored-By: Claude <claude@anthropic.ai>",
        "Co-Authored-By: claude[bot] <209825114+claude[bot]@users.noreply.github.com>",
        "Co-Authored-By: Claude Bot <claude-bot@bun.sh>",
        "Generated with Claude Code",
    )

    for message in messages:
        result = detect_commit_attribution({"message": f"Fix parser\n\n{message}"})
        assert result is not None, message
        assert result.tool == "claude_code", message
        assert result.evidence_type == "auto_declaration", message


def test_does_not_detect_humans_named_claude() -> None:
    messages = (
        "Co-Authored-By: Claude Paroz <claude@2xlibre.net>",
        "Co-Authored-By: Claude Martin <claude.martin@example.com>",
        "Co-Authored-By: Claude Opus 4.7 <noreply@unrelated.example>",
    )

    for message in messages:
        assert detect_commit_attribution({"message": message}) is None, message


def test_detects_devin_as_structural_evidence() -> None:
    result = detect_commit_attribution({"author_email": "devin-ai-integration@users.noreply.github.com"})

    assert result is not None
    assert result.tool == "devin"
    assert result.evidence_type == "structurelle"


def test_does_not_infer_unattributed_usage() -> None:
    assert detect_commit_attribution({"message": "Improve implementation with AI ideas"}) is None


def test_tags_dataframe() -> None:
    tagged = tag_commits(pd.DataFrame([
        {"message": "aider: add tests", "author_name": "Ada"},
        {"message": "docs: update", "author_name": "Lin"},
    ]))

    assert tagged["ai_attribue"].tolist() == [True, False]
    assert tagged.loc[0, "outil"] == "aider"
    assert pd.isna(tagged.loc[1, "outil"])