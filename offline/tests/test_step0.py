"""Tests for step0_fork_prs module."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from code_review_benchmark import step0_fork_prs as step0


class DummyCompletedProcess:
    def __init__(self, args: tuple[str, ...], returncode: int = 0):
        self.args = args
        self.returncode = returncode
        self.stdout = ""
        self.stderr = ""


def _make_forker() -> step0.GitHubPRForker:
    forker = step0.GitHubPRForker.__new__(step0.GitHubPRForker)
    forker.token = "token"
    forker.org = "my-org"
    forker._initialized_repos = set()
    forker._clone_cache = {}
    return forker


# ------------------------------------------------------------------
# URL parsing
# ------------------------------------------------------------------

def test_parse_pr_url_success():
    forker = _make_forker()
    owner, repo, number = forker.parse_pr_url("https://github.com/example/repo/pull/42")
    assert owner == "example"
    assert repo == "repo"
    assert number == 42


def test_parse_pr_url_invalid():
    forker = _make_forker()
    with pytest.raises(ValueError):
        forker.parse_pr_url("https://github.com/example/repo/issues/42")


# ------------------------------------------------------------------
# Repo name generation
# ------------------------------------------------------------------

def test_generate_repo_name_with_prefix(monkeypatch):
    class DummyDateTime:
        @staticmethod
        def now():
            return SimpleNamespace(strftime=lambda _: "20240201")

    monkeypatch.setattr(step0, "datetime", DummyDateTime)
    forker = _make_forker()

    result = forker.generate_repo_name("My Tool", config_prefix="cal_dot_com")
    assert result == "cal_dot_com__my-tool__20240201"


def test_generate_repo_name_without_prefix(monkeypatch):
    class DummyDateTime:
        @staticmethod
        def now():
            return SimpleNamespace(strftime=lambda _: "20240201")

    monkeypatch.setattr(step0, "datetime", DummyDateTime)
    forker = _make_forker()

    result = forker.generate_repo_name("My Tool", original_repo="my-upstream")
    assert result == "my-upstream__my-tool__20240201"


# ------------------------------------------------------------------
# Load URLs from file
# ------------------------------------------------------------------

def test_load_pr_urls_from_file(tmp_path):
    data = [
        {"url": "https://github.com/example/repo/pull/1"},
        {"pr_url": "https://github.com/example/repo/pull/2"},
        {"other": "ignored"},
    ]
    path = tmp_path / "prs.json"
    path.write_text(json.dumps(data))

    urls = step0._load_pr_urls_from_file(path)
    assert urls == [
        "https://github.com/example/repo/pull/1",
        "https://github.com/example/repo/pull/2",
    ]


# ------------------------------------------------------------------
# Branch fragment
# ------------------------------------------------------------------

def test_git_branch_fragment():
    frag = step0._git_branch_fragment("calcom", "cal.com", 8330)
    assert frag == "calcom-cal.com-8330"
    assert "/" not in frag


def test_git_branch_fragment_uniqueness():
    frag_a = step0._git_branch_fragment("keycloak", "keycloak", 42)
    frag_b = step0._git_branch_fragment("ai-code-review-evaluation", "keycloak-greptile", 1)
    assert frag_a != frag_b


# ------------------------------------------------------------------
# prepare_mirror_pr  (refspec push, no checkout)
# ------------------------------------------------------------------

def test_prepare_mirror_pr_uses_refspec_push(monkeypatch, tmp_path):
    class DummyDateTime:
        @staticmethod
        def now():
            return SimpleNamespace(strftime=lambda _: "20240201")

    monkeypatch.setattr(step0, "datetime", DummyDateTime)

    clone_dir = str(tmp_path / "clone")
    forker = _make_forker()
    forker._clone_cache[("owner", "repo")] = clone_dir

    git_calls: list[tuple[str, ...]] = []

    def fake_run_git(tmpdir: str, *args: str):
        git_calls.append(args)
        return DummyCompletedProcess(args)

    forker.run_git = fake_run_git  # type: ignore[assignment]
    forker.get_pr_details = lambda *_a, **_k: {  # type: ignore[assignment]
        "title": "Fix bug",
        "body": "Details",
        "base": {"sha": "abc1234"},
    }
    forker.ensure_repo_exists = lambda _name: False  # type: ignore[assignment]

    prepared = forker.prepare_mirror_pr(
        "https://github.com/owner/repo/pull/99",
        "My Tool",
        config_prefix="test_prefix",
    )

    assert isinstance(prepared, step0.PreparedMirrorPR)
    assert prepared.bench_repo_name == "test_prefix__my-tool__20240201"
    assert prepared.title == "Fix bug"
    assert prepared.head_branch == "pr-owner-repo-99"
    assert prepared.base_branch == "base-pr-owner-repo-99"

    # Verify: one fetch + one push (refspec), no checkout/branch/remote calls
    assert len(git_calls) == 2
    fetch_args = git_calls[0]
    assert fetch_args[0] == "fetch"
    assert "origin" in fetch_args
    assert "+pull/99/head:pr-fetch-owner-repo-99" in fetch_args

    push_args = git_calls[1]
    assert push_args[0] == "push"
    assert "abc1234:refs/heads/base-pr-owner-repo-99" in push_args
    assert "pr-fetch-owner-repo-99:refs/heads/pr-owner-repo-99" in push_args

    # No checkout or branch commands
    for call in git_calls:
        assert call[0] not in ("checkout", "branch", "remote"), (
            f"Unexpected git command: {call}"
        )


# ------------------------------------------------------------------
# open_mirror_pr
# ------------------------------------------------------------------

def test_open_mirror_pr_calls_create_pr():
    forker = _make_forker()
    called_with: dict = {}

    def fake_create_pr(**kwargs):
        called_with.update(kwargs)
        return {"html_url": "https://github.com/my-org/test/pull/1"}

    forker.create_pull_request = fake_create_pr  # type: ignore[assignment]

    prepared = step0.PreparedMirrorPR(
        pr_url="https://github.com/owner/repo/pull/1",
        config_prefix="test",
        bench_repo_name="test__my-tool__20240201",
        title="Title",
        body="Body",
        head_branch="pr-owner-repo-1",
        base_branch="base-pr-owner-repo-1",
    )

    result = forker.open_mirror_pr(prepared)
    assert result == {"new_pr_url": "https://github.com/my-org/test/pull/1"}
    assert called_with == {
        "repo": "test__my-tool__20240201",
        "title": "Title",
        "body": "Body",
        "head": "pr-owner-repo-1",
        "base": "base-pr-owner-repo-1",
    }


# ------------------------------------------------------------------
# process_pr  (end-to-end convenience wrapper)
# ------------------------------------------------------------------

def test_process_pr_happy_path(monkeypatch, tmp_path):
    class DummyDateTime:
        @staticmethod
        def now():
            return SimpleNamespace(strftime=lambda _: "20240201")

    monkeypatch.setattr(step0, "datetime", DummyDateTime)

    clone_dir = str(tmp_path / "clone")
    (tmp_path / "clone").mkdir()

    commands = []

    def fake_run(cmd, **_kwargs):
        commands.append(tuple(cmd))
        return DummyCompletedProcess(tuple(cmd))

    monkeypatch.setattr(step0.subprocess, "run", fake_run)

    forker = _make_forker()
    forker._clone_cache[("owner", "repo")] = clone_dir

    def fake_run_git(tmpdir: str, *args: str):
        return DummyCompletedProcess(args)

    forker.run_git = fake_run_git  # type: ignore[assignment]

    forker.get_pr_details = lambda *_a, **_k: {  # type: ignore[assignment]
        "title": "Add feature",
        "body": "Description",
        "base": {"ref": "main", "sha": "abc1234"},
    }
    forker.repo_exists = lambda _name: False  # type: ignore[assignment]
    forker.create_repo = lambda _name: None  # type: ignore[assignment]
    forker.disable_actions = lambda _name: None  # type: ignore[assignment]
    forker.disable_push_protection = lambda _name: None  # type: ignore[assignment]
    forker.make_repo_public = lambda _name: None  # type: ignore[assignment]

    monkeypatch.setattr(step0.time, "sleep", lambda _: None)

    expected_pr_url = "https://github.com/my-org/repo/pr/1"

    def fake_create_pr(**kwargs):
        assert kwargs == {
            "repo": "cal_dot_com__my-tool__20240201",
            "title": "Add feature",
            "body": "Description",
            "head": "pr-owner-repo-123",
            "base": "base-pr-owner-repo-123",
        }
        return {"html_url": expected_pr_url}

    forker.create_pull_request = fake_create_pr  # type: ignore[assignment]

    result = forker.process_pr(
        "https://github.com/owner/repo/pull/123",
        "My Tool",
        config_prefix="cal_dot_com",
    )

    assert result == {"new_pr_url": expected_pr_url}
