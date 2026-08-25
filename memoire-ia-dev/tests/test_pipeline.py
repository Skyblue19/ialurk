import pandas as pd
import pytest

from memoire_ia_dev.analysis import compare_periods
from memoire_ia_dev.cleaning import clean_commits
from memoire_ia_dev.metrics import add_year_and_period, build_annual_summary, build_quarterly_summary, commit_metrics
from memoire_ia_dev.policies import classify_policy
from memoire_ia_dev.prs import detect_pr_attribution
from memoire_ia_dev.validation import compare_to_reference, evaluate_aidev_full, normalize_aidev_pull_requests


def test_detects_structural_pr_signal() -> None:
    result = detect_pr_attribution({"author_login": "cursoragent", "author_type": "Bot"})

    assert result is not None
    assert result.tool == "cursor"
    assert result.evidence_type == "structurelle"


def test_detects_named_agent_accounts() -> None:
    logins = {
        "Copilot": "copilot",
        "devin-ai-integration[bot]": "devin",
        "google-labs-jules[bot]": "google_jules",
        "cursor[bot]": "cursor",
        "claudeai-v1[bot]": "claude_code",
    }

    for login, expected in logins.items():
        result = detect_pr_attribution({"author_login": login, "author_type": "Bot"})
        assert result is not None and result.tool == expected, login


def test_excludes_non_ai_automation_accounts() -> None:
    assert detect_pr_attribution({"author_login": "github-actions[bot]", "author_type": "Bot"}) is None
    assert detect_pr_attribution({"author_login": "dependabot[bot]", "author_type": "Bot"}) is None


def test_detects_agent_via_committer_identity() -> None:
    result = detect_pr_attribution({"author_login": "human-dev", "committer_login": "cursoragent"})

    assert result is not None
    assert result.tool == "cursor"
    assert result.signal == "committer_login"


def test_detects_agent_via_head_branch_convention() -> None:
    result = detect_pr_attribution({
        "author_login": "yegorsokolov", "author_type": "User", "head_ref": "codex/verify-mapping",
    })

    assert result is not None
    assert result.tool == "codex"
    assert result.evidence_type == "convention_branche"


def test_human_branch_without_agent_prefix_is_not_attributed() -> None:
    assert detect_pr_attribution({
        "author_login": "human-dev", "author_type": "User", "head_ref": "feature/add-login",
    }) is None


def test_detects_agent_task_links_in_body() -> None:
    codex = detect_pr_attribution({
        "author_login": "human-dev", "body": "View task at https://chatgpt.com/codex/tasks/abc",
    })
    cursor = detect_pr_attribution({
        "author_login": "human-dev", "body": "Opened via https://cursor.com/agents?id=xyz",
    })

    assert codex is not None and codex.tool == "codex"
    assert cursor is not None and cursor.tool == "cursor"
    assert codex.signal == "lien_agent"


def test_generic_bot_is_not_named_as_a_specific_tool() -> None:
    result = detect_pr_attribution({"author_login": "unknown-agent[bot]", "author_type": "Bot"})

    assert result is not None
    assert result.tool == "bot_generique"


def test_generic_bot_is_not_counted_as_ai_attribution() -> None:
    from memoire_ia_dev.prs import tag_prs

    tagged = tag_prs(pd.DataFrame([{"author_login": "unknown-agent[bot]", "author_type": "Bot"}]))

    assert bool(tagged.loc[0, "bot_generique_detecte"])
    assert not bool(tagged.loc[0, "ai_attribue"])


def test_annual_summary_keeps_commit_and_pr_channels_separate() -> None:
    commits = pd.DataFrame([{"annee": 2025, "depot": "org/repo", "ai_attribue": True, "outil": "copilot", "type_preuve": "auto_declaration"}])
    prs = pd.DataFrame([{"annee": 2025, "depot": "org/repo", "ai_attribue": False, "outil": None, "type_preuve": None}])

    result = build_annual_summary(commits, prs)

    assert result.loc[0, "nb_commits_ia"] == 1
    assert result.loc[0, "nb_prs_ia"] == 0


def test_quarterly_summary_separates_quarters() -> None:
    commits = add_year_and_period(pd.DataFrame([
        {"date": "2024-01-15", "depot": "org/repo", "ai_attribue": True, "outil": "copilot", "type_preuve": "structurelle"},
        {"date": "2024-04-15", "depot": "org/repo", "ai_attribue": False, "outil": None, "type_preuve": None},
    ]), "date")
    prs = add_year_and_period(pd.DataFrame([
        {"date": "2024-02-15", "depot": "org/repo", "ai_attribue": False, "outil": None, "type_preuve": None},
    ]), "date")

    result = build_quarterly_summary(commits, prs)

    assert result["annee_trimestre"].tolist() == ["2024Q1", "2024Q2"]
    assert result["nb_commits"].tolist() == [1, 1]
    assert result["nb_prs"].tolist() == [1, 0]


def test_before_after_metrics_exclude_merge_commits() -> None:
    commits = pd.DataFrame([
        {"identifiant": "one", "date": "2024-01-01", "is_merge": False, "lines_added": 4, "lines_deleted": 2},
        {"identifiant": "two", "date": "2024-05-01", "is_merge": True, "lines_added": 100, "lines_deleted": 100},
    ])
    prepared = add_year_and_period(commits, "date", "2024-03-01")
    result = commit_metrics(prepared)

    assert result["nb_commits"].sum() == 1
    assert result.loc[0, "taille_mediane"] == 6


def test_comparison_calculates_reference_metrics() -> None:
    extracted = pd.DataFrame([
        {"identifiant": "1", "ai_attribue": True},
        {"identifiant": "2", "ai_attribue": False},
        {"identifiant": "3", "ai_attribue": True},
    ])
    reference = pd.DataFrame({"pr_number": ["1", "2"]})

    result = compare_to_reference(extracted, reference, "identifiant", "pr_number")

    assert result == {"vrai_positif": 1, "faux_negatif": 1, "faux_positif": 1, "rappel": 0.5, "precision": 0.5}


def test_normalizes_observed_aidev_pull_request_columns() -> None:
    source = pd.DataFrame([{
        "number": 51,
        "repo_url": "https://api.github.com/repos/devhitoshi/call-generator",
        "agent": "Google_Jules",
    }])

    result = normalize_aidev_pull_requests(source)

    assert result.to_dict("records") == [{
        "depot": "devhitoshi/call-generator", "identifiant": "51", "outil_reference": "Google_Jules",
    }]


def test_cleaning_flags_automation_and_categories_without_dropping_rows() -> None:
    source = pd.DataFrame([{
        "author_name": "dependabot[bot]", "author_email": "bot@users.noreply.github.com",
        "lines_added": 2, "lines_deleted": 3, "message": "fix: update dependency",
    }])

    result = clean_commits(source)

    assert len(result) == 1
    assert result.loc[0, "bot_automation"]
    assert result.loc[0, "taille"] == 5
    assert result.loc[0, "categorie_tache"] == "fix"


def test_classifies_disclosure_policy_deterministically() -> None:
    assert classify_policy("You must disclose AI-generated code in pull requests.") == {"mention_ia": True, "niveau": "obligatoire"}
    assert classify_policy("This repository uses GitHub Actions.") == {"mention_ia": False, "niveau": "aucune_mention"}


def test_compare_periods_returns_non_parametric_result() -> None:
    pytest.importorskip("scipy")
    source = pd.DataFrame({"periode": ["avant", "avant", "apres", "apres"], "taille": [1, 2, 10, 11]})

    result = compare_periods(source, "taille")

    assert result["n_avant"] == 2
    assert result["n_apres"] == 2
    assert result["mediane_apres"] == 10.5


def test_full_aidev_evaluation_reports_recall_not_precision() -> None:
    reference = pd.DataFrame([{
        "number": 1, "title": "Generated by Replit", "body": "", "user": "agent", "agent": "Replit",
    }, {
        "number": 2, "title": "Add tests", "body": "", "user": "agent", "agent": "Cursor",
    }])

    report, records = evaluate_aidev_full(reference)

    assert report["n_reference"] == 2
    assert report["n_detecte"] == 1
    assert report["precision"] is None
    assert len(records) == 2


def test_full_aidev_evaluation_uses_commit_identities() -> None:
    reference = pd.DataFrame([{
        "id": 10, "number": 2, "title": "Add tests", "body": "", "user": "human-dev", "agent": "Cursor",
    }])
    commits = pd.DataFrame([{"pr_id": 10, "author": "human-dev", "committer": "cursoragent"}])

    report, records = evaluate_aidev_full(reference, commits)

    assert report["n_detecte"] == 1
    assert bool(records.loc[0, "donnees_commit"])