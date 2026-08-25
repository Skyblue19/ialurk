import pandas as pd

from memoire_ia_dev.detection import detect_commit_attribution, tag_commits


def test_detects_claude_trailer() -> None:
    result = detect_commit_attribution({"message": "Fix parser\n\nCo-Authored-By: Claude <noreply@anthropic.com>"})

    assert result is not None
    assert result.tool == "claude_code"
    assert result.evidence_type == "auto_declaration"


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