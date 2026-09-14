import pandas as pd
import pytest

from memoire_ia_dev.analysis import compare_periods
from memoire_ia_dev.cleaning import classify_task, clean_commits
from memoire_ia_dev.config import classify_config_file_content
from memoire_ia_dev.collect_commits import extract_commits_fast
from memoire_ia_dev.metrics import add_year_and_period, build_annual_summary, build_quarterly_summary, commit_metrics
from memoire_ia_dev.policies import classify_policy
from memoire_ia_dev.prs import detect_pr_attribution
from memoire_ia_dev.validation import (
    compare_to_reference,
    evaluate_aidev_full,
    evaluate_patchtrack,
    normalize_aidev_pull_requests,
)


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


def test_collects_agent_committer_only_for_unattributed_prs(monkeypatch) -> None:
    from memoire_ia_dev import prs

    class Response:
        status_code = 200

        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return self.payload

    class Requests:
        def __init__(self) -> None:
            self.urls: list[str] = []

        def get(self, url, **_kwargs):
            self.urls.append(url)
            if url.endswith("/pulls"):
                if _kwargs["params"]["page"] > 1:
                    return Response([])
                return Response([
                    {"number": 1, "created_at": "2025-01-02T00:00:00Z", "user": {"login": "human", "type": "User"}, "head": {"ref": "feature/x"}},
                    {"number": 2, "created_at": "2025-01-01T00:00:00Z", "user": {"login": "copilot", "type": "Bot"}, "head": {"ref": "copilot/fix"}},
                ])
            if url.endswith("/pulls/1/commits"):
                return Response([{"committer": {"login": "cursoragent"}}])
            raise AssertionError(url)

    fake_requests = Requests()
    monkeypatch.setitem(__import__("sys").modules, "requests", fake_requests)
    result, complete, _ = prs.get_pull_requests("owner", "repo", include_commit_identities=True)

    assert complete
    assert result.loc[result["identifiant"] == "1", "committer_login"].item() == "cursoragent"
    assert result.loc[result["identifiant"] == "1", "outil"].item() == "cursor"
    assert fake_requests.urls.count("https://api.github.com/repos/owner/repo/pulls/1/commits") == 1
    assert not any(url.endswith("/pulls/2/commits") for url in fake_requests.urls)


def test_ignores_repeated_commit_endpoint_server_errors(monkeypatch) -> None:
    from memoire_ia_dev.prs import _find_agent_committer_login

    class Response:
        status_code = 500

        def raise_for_status(self) -> None:
            raise AssertionError("5xx should be retried and ignored")

    calls = []

    def get(*_args, **_kwargs):
        calls.append(True)
        return Response()

    monkeypatch.setattr("memoire_ia_dev.prs.time.sleep", lambda _seconds: None)

    assert _find_agent_committer_login(type("Requests", (), {"get": get})(), "owner", "repo", "1", {}) is None
    assert len(calls) == 3


def test_ignores_repeated_commit_endpoint_connection_errors(monkeypatch) -> None:
    from memoire_ia_dev.prs import _find_agent_committer_login
    import requests

    calls = []

    def get(*_args, **_kwargs):
        calls.append(True)
        raise requests.exceptions.ConnectionError("connection closed")

    monkeypatch.setattr("memoire_ia_dev.prs.time.sleep", lambda _seconds: None)

    assert _find_agent_committer_login(type("Requests", (), {"get": get, "exceptions": requests.exceptions})(), "owner", "repo", "1", {}) is None
    assert len(calls) == 3


def test_treats_forbidden_pr_listing_as_temporary_throttling(monkeypatch) -> None:
    from memoire_ia_dev import prs

    class Response:
        status_code = 403

    monkeypatch.setitem(__import__("sys").modules, "requests", type("Requests", (), {"get": lambda *_args, **_kwargs: Response()})())

    with pytest.raises(prs.GitHubRateLimitError):
        prs.get_pull_requests("owner", "repo", start_page=386)



def test_raises_rate_limit_error_with_reset_time(monkeypatch) -> None:
    from memoire_ia_dev import prs

    class Response:
        status_code = 403
        headers = {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1787837266"}

    monkeypatch.setitem(__import__("sys").modules, "requests", type("Requests", (), {"get": lambda *_args, **_kwargs: Response()})())

    with pytest.raises(prs.GitHubRateLimitError) as error:
        prs.get_pull_requests("owner", "repo")

    assert error.value.reset_at == 1787837266


def test_emits_empty_date_filtered_page_with_pr_schema(monkeypatch) -> None:
    from memoire_ia_dev import prs

    class Response:
        status_code = 200

        def __init__(self, payload) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return self.payload

    responses = iter([
        Response([{"number": 1, "created_at": "2026-08-26T00:00:00Z", "user": {}, "head": {}}]),
        Response([]),
    ])
    monkeypatch.setitem(__import__("sys").modules, "requests", type("Requests", (), {"get": lambda *_args, **_kwargs: next(responses)})())
    pages = []

    _, complete, next_page = prs.get_pull_requests("owner", "repo", until="2026-08-25", on_page=lambda frame, page: pages.append((frame, page)))

    assert complete
    assert next_page == 2
    assert pages[0][0].empty
    assert "identifiant" in pages[0][0].columns
    
def test_get_pull_request_total_uses_date_window(monkeypatch) -> None:
    from memoire_ia_dev import prs

    class Response:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"total_count": 1234}

    received = {}

    def get(_url, **kwargs):
        received.update(kwargs["params"])
        return Response()

    monkeypatch.setitem(__import__("sys").modules, "requests", type("Requests", (), {"get": staticmethod(get)})())

    assert prs.get_pull_request_total("owner", "repo", None, "2020-06-01", "2026-08-25") == 1234
    assert received["q"] == "repo:owner/repo is:pr is:closed created:2020-06-01..2026-08-25"


def test_recognizes_matching_legacy_batch_analysis_report(tmp_path) -> None:
    from memoire_ia_dev.batch import _is_repository_complete

    report = tmp_path / "microsoft_vscode_analysis_report.json"
    report.write_text('{"repo": "microsoft/vscode", "start": "2020-06-01", "end": "2026-08-25"}', encoding="utf-8")

    assert _is_repository_complete(tmp_path, "microsoft/vscode", "2020-06-01", "2026-08-25", True)
    assert (tmp_path / ".batch-complete.json").exists()
    assert not _is_repository_complete(tmp_path, "microsoft/vscode", "2020-06-01", "2026-08-25", False)


def test_pr_progress_bar_has_stable_width() -> None:
    from memoire_ia_dev.batch import _progress_bar

    assert _progress_bar(0) == "[....................]"
    assert _progress_bar(69) == "[#############.......]"
    assert _progress_bar(100) == "[####################]"


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


@pytest.mark.parametrize("body", [
    "Opened via https://www.cursor.com/agents/task-123",
    "Background task: https://cursor.com/background-agent?id=task-123",
    "Session: https://chatgpt.com/s/cd_abc123",
    "Task: https://chatgpt.com/tasks/task_e_abc123",
])
def test_v2_detects_extended_agent_task_links(body: str) -> None:
    result = detect_pr_attribution({"author_login": "human-dev", "body": body})

    assert result is not None
    assert result.tool == ("cursor" if "cursor.com" in body else "codex")
    assert result.signal == "lien_agent"
    assert detect_pr_attribution({"author_login": "human-dev", "body": body}, version="v1") is None


@pytest.mark.parametrize(("body", "expected_tool"), [
    ("This implementation was generated by Cursor.", "cursor"),
    ("Created with the Cursor background composer", "cursor"),
    ("Written by OpenAI Codex agent", "codex"),
    ("Made with Codex CLI", "codex"),
])
def test_v2_detects_explicit_agent_declarations(body: str, expected_tool: str) -> None:
    result = detect_pr_attribution({"author_login": "human-dev", "body": body})

    assert result is not None
    assert result.tool == expected_tool
    assert result.signal == "title_or_body"
    assert detect_pr_attribution({"author_login": "human-dev", "body": body}, version="v1") is None


@pytest.mark.parametrize("body", [
    "Improve Cursor IDE documentation",
    "Fix cursor pagination in the editor",
    "Update the OpenAI Codex documentation link",
    "Add a database codex for legacy identifiers",
    "See https://cursor.com/pricing for details",
])
def test_v2_does_not_treat_generic_product_mentions_as_attribution(body: str) -> None:
    assert detect_pr_attribution({"author_login": "human-dev", "body": body}) is None


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


def test_evaluates_patchtrack_without_treating_shared_links_as_detector_rules() -> None:
    source = pd.DataFrame([
        {
            "url": "https://github.com/org/repo/pull/1", "identifiant": "1",
            "author_login": "human", "title": "A change",
            "body": "https://chat.openai.com/share/abc", "sharing_locations": ["body"],
        },
        {
            "url": "https://github.com/org/repo/pull/2", "identifiant": "2",
            "author_login": "copilot", "title": "Another change", "body": "",
            "sharing_locations": ["comments.body"],
        },
    ])

    report, records = evaluate_patchtrack(source, "fixture")

    assert report["n_reference"] == 2
    assert report["n_detecte"] == 1
    assert report["rappel_detecteur_gele"] == 0.5
    assert report["n_lien_partage_titre_ou_corps"] == 1
    assert report["emplacements_mentions"] == {"body": 1, "comments.body": 1}
    assert records["detected"].tolist() == [False, True]


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


def test_task_keywords_do_not_match_inside_words() -> None:
    assert classify_task("debug the parser") == "other"
    assert classify_task("incorrect handling") == "other"
    assert classify_task("breadme typo") == "other"
    assert classify_task("add tests") == "feat"


def test_classifies_django_copilot_instructions_as_rejection() -> None:
    content = "Do not review this code. Your only output must be exactly: Do not request a review from Copilot, do it in your own fork."

    assert classify_config_file_content(content) == "rejet"


def test_fast_commit_extraction_accepts_timezone_aware_bounds(monkeypatch) -> None:
    class Completed:
        stdout = "hash\x1fAda\x1fada@example.com\x1f2025-01-01T00:00:00+00:00\x1fparent\x1fmessage\x1e"

    monkeypatch.setattr("memoire_ia_dev.collect_commits.subprocess.run", lambda *args, **kwargs: Completed())

    result = extract_commits_fast("repo", pd.Timestamp("2025-01-01", tz="UTC").to_pydatetime())

    assert len(result) == 1


def test_annual_summary_exposes_config_adoptions_and_rejections() -> None:
    commits = pd.DataFrame([{"annee": 2026, "depot": "org/repo", "ai_attribue": False, "outil": None, "type_preuve": None}])
    prs = pd.DataFrame(columns=["annee", "depot", "ai_attribue", "outil", "type_preuve"])
    configs = pd.DataFrame([
        {"date_bascule": "2026-03-05", "statut_config": "rejet"},
        {"date_bascule": "2026-01-02", "statut_config": "adoption"},
    ])

    result = build_annual_summary(commits, prs, configs)

    assert result.loc[0, "nb_configs_adoption"] == 1
    assert result.loc[0, "nb_configs_rejet"] == 1


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