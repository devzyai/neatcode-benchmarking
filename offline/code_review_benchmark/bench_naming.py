"""Shared parsing for benchmark fork repo names and step0 head branch conventions.

Keeps step0_fork_prs, step1_download_prs, and step_speed_analysis aligned.
"""

from __future__ import annotations

import re
from typing import Any


def tool_slug_from_ai_name(ai_tool_name: str) -> str:
    """Normalize tool / ``--name`` to the slug used in bench repo names (matches step 0)."""
    return re.sub(r"[^a-zA-Z0-9]+", "-", ai_tool_name.lower()).strip("-")[:30]


def benchmark_repo_name_matches_tool(
    repo_name: str, tool_slug: str, date_yyyymmdd: str | None = None
) -> bool:
    """True if ``repo_name`` looks like a step-0 bench repo for ``tool_slug`` (and optional date)."""
    if date_yyyymmdd is not None:
        if not re.fullmatch(r"\d{8}", date_yyyymmdd):
            return False
        pat = rf".*__{re.escape(tool_slug)}__{re.escape(date_yyyymmdd)}$"
        return bool(re.fullmatch(pat, repo_name))
    pat = rf".*__{re.escape(tool_slug)}__\d{{8}}$"
    return bool(re.fullmatch(pat, repo_name))


def original_pr_number_from_head_ref(head_ref: str) -> int | None:
    """Recover upstream PR number from benchmark PR head branch name.

    Supports:
    - Legacy: ``pr-8330`` (digits only after ``pr-``).
    - Current: ``pr-{owner}-{repo}-…-{n}`` where ``{n}`` is the upstream PR number
      (same contract as ``_git_branch_fragment`` in step0).
    """
    if not head_ref.startswith("pr-"):
        return None
    rest = head_ref[3:]
    if rest.isdigit():
        return int(rest)
    m = re.search(r"-(\d+)$", rest)
    return int(m.group(1)) if m else None


def parse_bench_repo_name(name: str) -> dict | None:
    """Parse benchmark repository name under the org.

    Tries **in order**:

    1. **Old** — one upstream PR per repo, PR encoded in name:
       ``{config}__{original_repo}__{tool}__PR{n}__{date}``
    2. **Legacy shared** — multiple PRs per repo, upstream repo in name:
       ``{config}__{original_repo}__{tool}__{date}`` (``date`` = YYYYMMDD)
    3. **Shared (post fix/pr-request-failure)** — one bench repo per golden JSON file:
       ``{config}__{tool}__{date}`` (no upstream repo segment; use
       :func:`find_golden_url_for_config` to match goldens).

    Returns dict keys: ``config_prefix``, ``tool``, ``date``, ``pr_number`` (int or
    ``None`` for shared repos), ``original_repo`` (``str`` or ``None`` for format 3).
    """
    # 1) Old format (one PR per repo)
    match = re.match(r"^(.+?)__(.+?)__(.+?)__PR(\d+)__(\d+)$", name)
    if match:
        return {
            "config_prefix": match.group(1),
            "original_repo": match.group(2),
            "tool": match.group(3),
            "pr_number": int(match.group(4)),
            "date": match.group(5),
        }
    # 2) Legacy four-part shared multi-PR (original_repo + tool + date)
    match = re.match(r"^(.+?)__(.+?)__(.+?)__(\d{8})$", name)
    if match:
        return {
            "config_prefix": match.group(1),
            "original_repo": match.group(2),
            "tool": match.group(3),
            "pr_number": None,
            "date": match.group(4),
        }
    # 3) Three-part shared multi-PR (one bench repo per golden JSON file)
    match = re.match(r"^(.+?)__(.+?)__(\d{8})$", name)
    if match:
        return {
            "config_prefix": match.group(1),
            "original_repo": None,
            "tool": match.group(2),
            "pr_number": None,
            "date": match.group(3),
        }
    return None


def find_golden_url(
    golden: dict[str, dict], original_repo: str, pr_number: int
) -> str | None:
    """Match golden PR URL by upstream repo name and PR number (boundary-safe)."""
    pat = re.compile(
        rf"github\.com/[^/]+/{re.escape(original_repo)}/pull/{pr_number}(?!\d)"
    )
    for url in golden:
        if pat.search(url):
            return url
    return None


def find_golden_url_for_config(
    golden: dict[str, dict], config_prefix: str, pr_number: int
) -> str | None:
    """Match golden PR URL by ``golden_comments/{config_prefix}.json`` and PR number."""
    expected_file = f"{config_prefix}.json"
    # Avoid matching /pull/1 inside /pull/12
    needle = re.compile(rf"/pull/{pr_number}(?!\d)")
    for url, meta in golden.items():
        if meta.get("source_file") != expected_file:
            continue
        if needle.search(url):
            return url
    return None


def source_repo_from_github_pr_url(url: str) -> str | None:
    """Return repo segment from a ``https://github.com/{owner}/{repo}/pull/{n}`` URL."""
    m = re.search(r"github\.com/[^/]+/([^/]+)/pull/\d+", url)
    return m.group(1) if m else None


def extract_benchmark_prs_from_pulls_json(prs: list[Any] | Any) -> list[dict]:
    """Turn GitHub ``/pulls`` API JSON into tasks with upstream PR numbers."""
    if not isinstance(prs, list):
        return []
    results: list[dict] = []
    for pr in prs:
        head_ref = pr.get("head", {}).get("ref", "") if isinstance(pr, dict) else ""
        orig = original_pr_number_from_head_ref(head_ref)
        if orig is not None:
            results.append({
                "repo_pr_number": pr["number"],
                "original_pr_number": orig,
                "pr_url": pr.get("html_url"),
            })
    return results
