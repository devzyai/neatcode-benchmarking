#!/usr/bin/env python3
"""Aggregate PR review comments from benchmark repos with golden comments."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from tqdm import tqdm

# GitHub API allows ~30 concurrent requests, stay conservative
MAX_WORKERS = 15


def load_dotenv(filepath: str = ".env") -> None:
    """Load environment variables from .env file."""
    env_path = Path(filepath)
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                os.environ.setdefault(key, value)


def gh(args: list[str]) -> dict | list:
    """Run gh CLI command and return parsed JSON."""
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        if "gh auth login" in result.stderr or "GH_TOKEN" in result.stderr:
            print("Error: GitHub CLI not authenticated.", file=sys.stderr)
            print("Run 'gh auth login' or set GH_TOKEN environment variable.", file=sys.stderr)
            sys.exit(1)
        raise subprocess.CalledProcessError(result.returncode, ["gh", *args], result.stdout, result.stderr)
    return json.loads(result.stdout) if result.stdout.strip() else {}


def load_golden_comments(folder: str) -> dict[str, dict]:
    """Load all golden comment files into lookup dict keyed by URL."""
    golden = {}
    folder_path = Path(folder)
    for json_file in folder_path.glob("*.json"):
        with open(json_file) as f:
            entries = json.load(f)
        for entry in entries:
            url = entry["url"]
            golden[url] = {
                "pr_title": entry.get("pr_title"),
                "original_url": entry.get("original_url"),
                "az_comment": entry.get("az_comment"),
                "comments": entry.get("comments", []),
                "source_file": json_file.name,
            }
    return golden


def parse_repo_name(name: str) -> dict | None:
    """Parse benchmark repo name to extract components.

    Supports two naming conventions:
      New: {config_prefix}__{original_repo}__{tool}__{date}
      Old: {config_prefix}__{original_repo}__{tool}__PR{number}__{date}
    """
    # New format (no PR number — repo holds multiple PRs)
    match = re.match(r"^(.+?)__(.+?)__(.+?)__(\d{8})$", name)
    if match:
        return {
            "config_prefix": match.group(1),
            "original_repo": match.group(2),
            "tool": match.group(3),
            "pr_number": None,
            "date": match.group(4),
        }
    # Old format (one PR per repo)
    match = re.match(r"^(.+?)__(.+?)__(.+?)__PR(\d+)__(\d+)$", name)
    if match:
        return {
            "config_prefix": match.group(1),
            "original_repo": match.group(2),
            "tool": match.group(3),
            "pr_number": int(match.group(4)),
            "date": match.group(5),
        }
    return None


def find_golden_url(golden: dict[str, dict], original_repo: str, pr_number: int) -> str | None:
    """Find golden comment URL matching repo and PR number."""
    for url in golden:
        if f"/{original_repo}/pull/{pr_number}" in url:
            return url
    return None


def fetch_review_comments(org: str, repo: str, pr: int) -> list[dict]:
    """Fetch all review comments from a PR."""
    comments = []

    # Fetch PR review comments (inline code comments)
    try:
        review_comments = gh(["api", f"/repos/{org}/{repo}/pulls/{pr}/comments"])
        for c in review_comments:
            comments.append({
                "path": c.get("path"),
                "line": c.get("line") or c.get("original_line"),
                "body": c.get("body"),
                "created_at": c.get("created_at"),
            })
    except subprocess.CalledProcessError:
        pass

    # Fetch PR review bodies (top-level review comments)
    try:
        reviews = gh(["api", f"/repos/{org}/{repo}/pulls/{pr}/reviews"])
        for r in reviews:
            if r.get("body"):
                comments.append({
                    "path": None,
                    "line": None,
                    "body": r.get("body"),
                    "created_at": r.get("submitted_at"),
                })
    except subprocess.CalledProcessError:
        pass

    # Fetch issue comments (general PR comments)
    try:
        issue_comments = gh(["api", f"/repos/{org}/{repo}/issues/{pr}/comments"])
        for c in issue_comments:
            comments.append({
                "path": None,
                "line": None,
                "body": c.get("body"),
                "created_at": c.get("created_at"),
            })
    except subprocess.CalledProcessError:
        pass

    return comments


def fetch_pr_metadata(org: str, repo: str, pr: int) -> dict:
    """Fetch PR title and URL."""
    try:
        pr_data = gh(["api", f"/repos/{org}/{repo}/pulls/{pr}"])
        return {
            "title": pr_data.get("title"),
            "url": pr_data.get("html_url"),
        }
    except subprocess.CalledProcessError:
        return {"title": None, "url": None}


def list_repo_prs(org: str, repo_name: str) -> list[dict]:
    """List open PRs in a new-format repo and extract original PR numbers from branch names.

    Returns a list of dicts with ``repo_pr_number`` (the PR number inside the
    benchmarking repo) and ``original_pr_number`` (extracted from the ``pr-{N}``
    head branch convention used by step0).
    """
    prs = gh(["api", f"/repos/{org}/{repo_name}/pulls?state=open&per_page=100"])
    if not isinstance(prs, list):
        return []
    results = []
    for pr in prs:
        head_ref = pr.get("head", {}).get("ref", "")
        match = re.match(r"^pr-(\d+)$", head_ref)
        if match:
            results.append({
                "repo_pr_number": pr["number"],
                "original_pr_number": int(match.group(1)),
            })
    return results


def fetch_repo_data(org: str, repo_name: str, pr_number: int = 1) -> dict:
    """Fetch both PR metadata and comments for a repo. Returns combined result."""
    pr_meta = fetch_pr_metadata(org, repo_name, pr_number)
    comments = fetch_review_comments(org, repo_name, pr_number)
    return {
        "repo_name": repo_name,
        "pr_meta": pr_meta,
        "comments": comments,
    }


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Aggregate benchmark PR comments with golden comments")
    parser.add_argument("--org", default="code-review-benchmark", help="GitHub organization")
    parser.add_argument("--output", default="benchmark_data.json", help="Output JSON file")
    parser.add_argument("--golden", default="golden_comments", help="Golden comments folder")
    parser.add_argument("--test", action="store_true", help="Test mode: process 1 repo per tool")
    parser.add_argument("--tool", help="Only process specific tool")
    parser.add_argument("--force", action="store_true", help="Force refetch (all tools, or specific with --tool)")
    args = parser.parse_args()

    # Load existing output for incremental processing
    output_path = Path(args.output)
    if output_path.exists():
        with open(output_path) as f:
            output = json.load(f)
        print(f"Loaded {len(output)} existing entries from {args.output}")
    else:
        output = {}

    # Load golden comments
    golden = load_golden_comments(args.golden)
    print(f"Loaded {len(golden)} golden comment entries")

    # List all repos in org
    print(f"Fetching repos from {args.org}...")
    repos = gh(["repo", "list", args.org, "--limit", "5000", "--json", "name"])
    print(f"Found {len(repos)} repos")

    # Build list of repos to process.
    # Each entry: (repo_name, parsed, golden_url, repo_pr_number)
    #   repo_pr_number = the PR number inside the benchmark repo to fetch.
    tools_seen = set()
    to_process: list[tuple[str, dict, str, int]] = []
    skipped = 0
    errors = []

    def _maybe_enqueue(repo_name: str, parsed: dict, golden_url: str, repo_pr_number: int):
        nonlocal skipped
        tool = parsed["tool"]
        if golden_url in output:
            existing_reviews = {r["tool"]: r for r in output[golden_url].get("reviews", [])}
            if tool in existing_reviews:
                if args.force:
                    output[golden_url]["reviews"] = [
                        r for r in output[golden_url]["reviews"] if r["tool"] != tool
                    ]
                else:
                    skipped += 1
                    return
        to_process.append((repo_name, parsed, golden_url, repo_pr_number))

    for repo_entry in repos:
        repo_name = repo_entry["name"]
        parsed = parse_repo_name(repo_name)

        if not parsed:
            continue

        tool = parsed["tool"]

        if args.tool and tool != args.tool:
            continue

        if args.test and tool in tools_seen:
            continue

        if parsed["pr_number"] is not None:
            # Old format: single PR per repo (always PR #1 in the benchmark repo)
            golden_url = find_golden_url(golden, parsed["original_repo"], parsed["pr_number"])
            if not golden_url:
                errors.append(f"No golden match for {repo_name}")
                continue
            _maybe_enqueue(repo_name, parsed, golden_url, 1)
        else:
            # New format: repo holds multiple PRs — list them
            try:
                repo_prs = list_repo_prs(args.org, repo_name)
            except Exception as e:
                errors.append(f"Error listing PRs for {repo_name}: {e}")
                continue
            for pr_info in repo_prs:
                orig_num = pr_info["original_pr_number"]
                golden_url = find_golden_url(golden, parsed["original_repo"], orig_num)
                if not golden_url:
                    errors.append(f"No golden match for {repo_name} PR#{orig_num}")
                    continue
                parsed_with_pr = {**parsed, "pr_number": orig_num}
                _maybe_enqueue(repo_name, parsed_with_pr, golden_url, pr_info["repo_pr_number"])

        tools_seen.add(tool)

        if args.test and len(tools_seen) >= 3:
            break

    print(f"To process: {len(to_process)}, skipped: {skipped}")

    if not to_process:
        print("Nothing to do.")
        return

    # Fetch all repos concurrently
    processed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_info = {
            executor.submit(fetch_repo_data, args.org, repo_name, repo_pr_number): (repo_name, parsed, golden_url)
            for repo_name, parsed, golden_url, repo_pr_number in to_process
        }

        with tqdm(total=len(to_process), desc="Fetching reviews") as pbar:
            for future in as_completed(future_to_info):
                repo_name, parsed, golden_url = future_to_info[future]
                tool = parsed["tool"]

                try:
                    result = future.result()
                except Exception as e:
                    errors.append(f"Error fetching {repo_name}: {e}")
                    pbar.update(1)
                    continue

                # Create or update entry
                if golden_url not in output:
                    golden_data = golden[golden_url]
                    output[golden_url] = {
                        "pr_title": golden_data["pr_title"],
                        "original_url": golden_data["original_url"],
                        "source_repo": parsed["original_repo"],
                        "golden_comments": golden_data["comments"],
                        "golden_source_file": golden_data["source_file"],
                        "az_comment": golden_data["az_comment"],
                        "reviews": [],
                    }

                output[golden_url]["reviews"].append({
                    "tool": tool,
                    "repo_name": repo_name,
                    "pr_url": result["pr_meta"]["url"],
                    "review_comments": result["comments"],
                })

                processed += 1
                pbar.update(1)

                # Save periodically (every 50)
                if processed % 50 == 0:
                    with open(output_path, "w") as f:
                        json.dump(output, f, indent=2)

    # Strip any model-specific data (candidates) before saving raw PR data
    for entry in output.values():
        for review in entry.get("reviews", []):
            review.pop("candidates", None)

    # Final save
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    # Summary
    print("\nSummary:")
    print(f"  Processed: {processed}")
    print(f"  Skipped (already loaded): {skipped}")
    print(f"  Errors: {len(errors)}")
    for err in errors[:10]:
        print(f"    - {err}")
    if len(errors) > 10:
        print(f"    ... and {len(errors) - 10} more")


if __name__ == "__main__":
    main()
