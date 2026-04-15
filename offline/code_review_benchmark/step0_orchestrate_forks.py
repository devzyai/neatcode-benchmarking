#!/usr/bin/env python3
"""Orchestrate benchmark repo forking and concurrent PR creation.

Three-stage pipeline:
  Stage 1  Clone unique upstream repos + create benchmark repos (serial).
  Stage 2  Fetch + refspec-push branches for every PR (parallel, lock-free).
  Stage 3  Open GitHub PRs via API (parallel, configurable concurrency).

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

from code_review_benchmark.step0_fork_prs import GitHubPRForker
from code_review_benchmark.step0_fork_prs import PreparedMirrorPR
from code_review_benchmark.step0_fork_prs import _load_pr_urls_from_file
from code_review_benchmark.step0_fork_prs import load_dotenv


# ---------------------------------------------------------------------------
# Stage 1 helpers
# ---------------------------------------------------------------------------

def _collect_work_items(
    forker: GitHubPRForker,
    selected_files: list[Path],
    tool_name: str,
    prs_per_repo: int,
) -> tuple[list[tuple[str, str]], int]:
    """Scan golden files, bootstrap bench repos, clone upstreams.

    Returns (work_items, bootstrap_failure_count) where each work item is
    ``(config_prefix, pr_url)``.
    """
    work_items: list[tuple[str, str]] = []
    upstreams_seen: set[tuple[str, str]] = set()
    bootstrap_failures = 0

    for repo_file in selected_files:
        config_prefix = repo_file.stem
        urls = _load_pr_urls_from_file(str(repo_file))
        urls = urls[:prs_per_repo]
        if not urls:
            print(f"\n[{config_prefix}] No PR URLs found, skipping.")
            continue

        # --- Bootstrap the single bench repo for this golden file ---
        print(f"\n[{config_prefix}] Bootstrapping target repository...")
        try:
            bench_repo = forker.generate_repo_name(tool_name, config_prefix)
            newly_created = forker.ensure_repo_exists(bench_repo)
            if newly_created:
                print(f"  Making repository public: {forker.org}/{bench_repo}")
                forker.make_repo_public(bench_repo)
            else:
                print(f"  Using existing repository: {forker.org}/{bench_repo}")
            print(f"[{config_prefix}] Target repo ready: {forker.org}/{bench_repo}")
        except Exception as exc:
            bootstrap_failures += len(urls)
            print(f"[{config_prefix}] Bootstrap failed: {exc}", file=sys.stderr)
            continue

        # --- Collect unique upstreams for cloning ---
        for url in urls:
            try:
                owner, repo, _ = forker.parse_pr_url(url)
                key = (owner, repo)
                if key not in upstreams_seen:
                    upstreams_seen.add(key)
            except ValueError:
                pass
            work_items.append((config_prefix, url))

    # --- Clone all unique upstream repos (serial) ---
    print(f"\n=== Stage 1: Cloning {len(upstreams_seen)} unique upstream repo(s) ===")
    for owner, repo in sorted(upstreams_seen):
        try:
            forker.clone_upstream(owner, repo)
        except Exception as exc:
            print(f"  Clone failed for {owner}/{repo}: {exc}", file=sys.stderr)

    return work_items, bootstrap_failures


# ---------------------------------------------------------------------------
# Stage 2 / 3 task wrappers
# ---------------------------------------------------------------------------

def _prepare_task(
    forker: GitHubPRForker,
    tool_name: str,
    config_prefix: str,
    pr_url: str,
) -> PreparedMirrorPR:
    return forker.prepare_mirror_pr(pr_url, tool_name, config_prefix)


def _open_task(
    forker: GitHubPRForker,
    prepared: PreparedMirrorPR,
) -> dict:
    return forker.open_mirror_pr(prepared)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Three-stage pipeline: clone, prepare branches, open PRs."
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
        "--prepare-concurrency",
        type=int,
        default=10,
        help="Parallel fetch+push tasks in stage 2 (default: 10)",
    )
    parser.add_argument(
        "--pr-open-concurrency",
        type=int,
        default=10,
        help="Parallel POST /pulls calls in stage 3 (default: 10)",
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

    # ------------------------------------------------------------------
    # Stage 1: clone upstreams + bootstrap bench repos (serial)
    # ------------------------------------------------------------------
    forker = GitHubPRForker(args.token, args.org)
    work_items, bootstrap_failures = _collect_work_items(
        forker, selected_files, args.name, args.prs_per_repo
    )

    if not work_items:
        print("No work items to process.")
        sys.exit(1 if bootstrap_failures else 0)

    # ------------------------------------------------------------------
    # Stage 2: fetch + refspec push (parallel, lock-free)
    # ------------------------------------------------------------------
    print(f"\n=== Stage 2: Preparing {len(work_items)} PR(s) "
          f"with {min(args.prepare_concurrency, len(work_items))} worker(s) ===")

    prepared: list[PreparedMirrorPR] = []
    prepare_failures = 0

    with ThreadPoolExecutor(
        max_workers=min(args.prepare_concurrency, len(work_items))
    ) as executor:
        futures = {}
        for config_prefix, pr_url in work_items:
            future = executor.submit(_prepare_task, forker, args.name, config_prefix, pr_url)
            futures[future] = pr_url

        for future in as_completed(futures):
            pr_url = futures[future]
            try:
                result = future.result()
                prepared.append(result)
            except Exception as exc:
                prepare_failures += 1
                print(f"  PREPARE FAIL: {pr_url} -> {exc}", file=sys.stderr)

    print(f"\nStage 2 done: {len(prepared)} prepared, {prepare_failures} failed")

    if not prepared:
        print("No PRs prepared successfully. Nothing to open.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Stage 3: open PRs via API (parallel)
    # ------------------------------------------------------------------
    print(f"\n=== Stage 3: Opening {len(prepared)} PR(s) "
          f"with {min(args.pr_open_concurrency, len(prepared))} worker(s) ===")

    open_success = 0
    open_failures = 0

    with ThreadPoolExecutor(
        max_workers=min(args.pr_open_concurrency, len(prepared))
    ) as executor:
        futures = {}
        for item in prepared:
            future = executor.submit(_open_task, forker, item)
            futures[future] = item.pr_url

        for future in as_completed(futures):
            pr_url = futures[future]
            try:
                result = future.result()
                open_success += 1
                print(f"  OPEN OK: {pr_url} -> {result.get('new_pr_url')}")
            except Exception as exc:
                open_failures += 1
                print(f"  OPEN FAIL: {pr_url} -> {exc}", file=sys.stderr)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    total_failures = bootstrap_failures + prepare_failures + open_failures
    print("\n=== Orchestration Summary ===")
    print(f"Prepared : {len(prepared)}/{len(work_items)}")
    print(f"Opened   : {open_success}/{len(prepared)}")
    print(f"Failures : {total_failures} "
          f"(bootstrap={bootstrap_failures}, prepare={prepare_failures}, open={open_failures})")

    if total_failures > 0:
        sys.exit(1)

    print("All steps completed successfully.")


if __name__ == "__main__":
    main()
