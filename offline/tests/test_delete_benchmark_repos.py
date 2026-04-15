"""Tests for bench naming helpers used by delete_benchmark_repos and filter logic."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from code_review_benchmark import delete_benchmark_repos as dbr
from code_review_benchmark.bench_naming import benchmark_repo_name_matches_tool
from code_review_benchmark.bench_naming import tool_slug_from_ai_name


def test_tool_slug_from_ai_name_matches_step0_contract():
    assert tool_slug_from_ai_name("NeatCode Staging!!") == "neatcode-staging"
    assert tool_slug_from_ai_name("a" * 50) == "a" * 30


@pytest.mark.parametrize(
    "repo_name,tool_slug,date,expected",
    [
        ("cal_dot_com__neatcode-staging__20260401", "neatcode-staging", None, True),
        ("getsentry__sentry__neatcode-staging__20260401", "neatcode-staging", None, True),
        ("cal_dot_com__other-tool__20260401", "neatcode-staging", None, False),
        ("cal_dot_com__neatcode-staging__20260401", "neatcode-staging", "20260401", True),
        ("cal_dot_com__neatcode-staging__20260402", "neatcode-staging", "20260401", False),
        ("no-date-suffix", "neatcode-staging", None, False),
    ],
)
def test_benchmark_repo_name_matches_tool(repo_name, tool_slug, date, expected):
    assert benchmark_repo_name_matches_tool(repo_name, tool_slug, date) == expected


def test_filter_benchmark_repos():
    names = [
        "cal_dot_com__neatcode-staging__20260401",
        "other__neatcode-staging__20260401",
        "cal_dot_com__other__20260401",
    ]
    slug = tool_slug_from_ai_name("neatcode_staging")
    assert dbr.filter_benchmark_repos(names, slug, None) == [
        "cal_dot_com__neatcode-staging__20260401",
        "other__neatcode-staging__20260401",
    ]
    assert dbr.filter_benchmark_repos(names, slug, "20260401") == [
        "cal_dot_com__neatcode-staging__20260401",
        "other__neatcode-staging__20260401",
    ]


def test_list_repos_api_path_falls_back_to_users_on_org_404(monkeypatch):
    def fake_gh(args: list[str]):
        url = args[-1]
        if "orgs/dezy-benchmark" in url:
            return SimpleNamespace(returncode=1, stdout="", stderr="HTTP 404: Not Found")
        if "users/dezy-benchmark" in url:
            return SimpleNamespace(returncode=0, stdout="[]", stderr="")
        raise AssertionError(url)

    monkeypatch.setattr(dbr, "_run_gh", fake_gh)
    assert dbr._list_repos_api_path("dezy-benchmark") == "users/dezy-benchmark"
