#!/usr/bin/env python3
"""Orchestrate benchmark repo forking and concurrent PR creation.

Behavior:
- Creates each benchmark target repo once (one per golden_comments JSON file).
- Creates up to N PRs per repo (default: 10) concurrently.
- Waits for all PR creations to finish and returns non-zero on failures.

Usage:
    uv run python -m code_review_benchmark.step0_orchestrate_forks \
        --org code-review-benchmark \
        --name coderabbit \
        --golden-dir golden_comments
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed
import os
from pathlib import Path
import sys
from typing import Any

from code_review_benchmark.step0_fork_prs import GitHubPRForker
from code_review_benchmark.step0_fork_prs import _load_pr_urls_from_file


def _bootstrap_repo(
    token: str,
    org: str,
    tool_name: str,
    config_prefix: str,
    sample_pr_url: str,
) -> str:
    """Ensure target benchmark repo exists once and is public."""
    forker = GitHubPRForker(token, org)
    owner, source_repo, _ = forker.parse_pr_url(sample_pr_url)
    del owner  # Owner only needed for URL parsing validation.
    target_repo_name = forker.generate_repo_name(source_repo, tool_name, config_prefix)
    newly_created = forker.ensure_repo_exists(target_repo_name)
    if newly_created:
        print(f"Making repository public: {org}/{target_repo_name}")
        forker.make_repo_public(target_repo_name)
    else:
        print(f"Using existing repository: {org}/{target_repo_name}")
    return target_repo_name


def _create_pr_task(
    token: str,
    org: str,
    tool_name: str,
    config_prefix: str,
    pr_url: str,
) -> dict[str, Any]:
    """Create a single PR in the pre-created benchmark repo."""
    forker = GitHubPRForker(token, org)
    return forker.process_pr(pr_url, tool_name, config_prefix)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create benchmark repos once, then create PRs concurrently."
    )
    parser.add_argument("--org", required=True, help="Target GitHub organization")
    parser.add_argument("--name", required=True, help="AI tool slug/name for repo naming")
    parser.add_argument(
        "--token",
        default=os.environ.get("GITHUB_TOKEN"),
        help="GitHub token (defaults to GITHUB_TOKEN)",
    )
    parser.add_argument(
        "--golden-dir",
        default="golden_comments",
        help="Directory containing golden comment JSON files",
    )
    parser.add_argument(
        "--repos",
        type=int,
        default=5,
        help="How many golden JSON files (repos) to process (default: 5)",
    )
    parser.add_argument(
        "--prs-per-repo",
        type=int,
        default=10,
        help="How many PR URLs per repo file to process (default: 10)",
    )
    parser.add_argument(
        "--workers-per-repo",
        type=int,
        default=10,
        help="Concurrent PR workers per repo (default: 10)",
    )
    args = parser.parse_args()

    if not args.token:
        print("Error: Set GITHUB_TOKEN or pass --token", file=sys.stderr)
        sys.exit(1)

    golden_dir = Path(args.golden_dir)
    if not golden_dir.exists() or not golden_dir.is_dir():
        print(f"Error: golden directory not found: {golden_dir}", file=sys.stderr)
        sys.exit(1)

    json_files = sorted(golden_dir.glob("*.json"))
    if not json_files:
        print(f"Error: no JSON files found in {golden_dir}", file=sys.stderr)
        sys.exit(1)

    selected_files = json_files[: args.repos]
    print(f"Processing {len(selected_files)} repo file(s): {[p.name for p in selected_files]}")

    total_success = 0
    total_failures = 0

    for repo_file in selected_files:
        config_prefix = repo_file.stem
        urls = _load_pr_urls_from_file(str(repo_file))
        urls = urls[: args.prs_per_repo]
        if not urls:
            print(f"\n[{config_prefix}] No PR URLs found, skipping.")
            continue

        print(f"\n[{config_prefix}] Bootstrapping target repository...")
        try:
            target_repo = _bootstrap_repo(
                token=args.token,
                org=args.org,
                tool_name=args.name,
                config_prefix=config_prefix,
                sample_pr_url=urls[0],
            )
            print(f"[{config_prefix}] Target repo ready: {args.org}/{target_repo}")
        except Exception as exc:
            total_failures += len(urls)
            print(f"[{config_prefix}] Bootstrap failed: {exc}", file=sys.stderr)
            continue

        print(
            f"[{config_prefix}] Creating {len(urls)} PR(s) with "
            f"{min(args.workers_per_repo, len(urls))} worker(s)..."
        )
        futures = {}
        with ThreadPoolExecutor(
            max_workers=min(args.workers_per_repo, len(urls))
        ) as executor:
            for pr_url in urls:
                future = executor.submit(
                    _create_pr_task,
                    args.token,
                    args.org,
                    args.name,
                    config_prefix,
                    pr_url,
                )
                futures[future] = pr_url

            repo_success = 0
            repo_failures = 0
            for future in as_completed(futures):
                pr_url = futures[future]
                try:
                    result = future.result()
                    repo_success += 1
                    print(f"[{config_prefix}] OK: {pr_url} -> {result.get('new_pr_url')}")
                except Exception as exc:
                    repo_failures += 1
                    print(f"[{config_prefix}] FAIL: {pr_url} -> {exc}", file=sys.stderr)

        total_success += repo_success
        total_failures += repo_failures
        print(
            f"[{config_prefix}] Completed: success={repo_success}, failures={repo_failures}"
        )

    print("\n=== Orchestration Summary ===")
    print(f"Success: {total_success}")
    print(f"Failures: {total_failures}")

    if total_failures > 0:
        sys.exit(1)

    print("All steps completed successfully.")


if __name__ == "__main__":
    main()

