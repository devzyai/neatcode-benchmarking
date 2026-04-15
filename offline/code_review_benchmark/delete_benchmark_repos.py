#!/usr/bin/env python3
"""List and optionally delete benchmark fork repos (step 0 naming).

Default is dry-run: prints matching repo names. Pass --execute to delete.

Requires ``gh`` authenticated (``gh auth login`` or ``GH_TOKEN``). GitHub-hosted
runners include ``gh``; no extra install step is needed there.

``--org`` may be a GitHub **Organization** or a **user** login. If
``/orgs/{name}/repos`` returns 404, listing falls back to ``/users/{name}/repos``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

from .bench_naming import benchmark_repo_name_matches_tool
from .bench_naming import tool_slug_from_ai_name
from .step1_download_prs import load_dotenv


def _run_gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
    )


def _gh_not_found(proc: subprocess.CompletedProcess[str]) -> bool:
    err = (proc.stderr or "") + (proc.stdout or "")
    return proc.returncode != 0 and ("404" in err or "Not Found" in err)


def _list_repos_api_path(owner: str) -> str:
    """Return ``orgs/OWNER`` or ``users/OWNER`` for ``GET .../repos`` listing."""
    probe = _run_gh(
        [
            "api",
            "-H",
            "Accept: application/vnd.github+json",
            f"orgs/{owner}/repos?per_page=1&page=1",
        ]
    )
    if probe.returncode == 0:
        return f"orgs/{owner}"
    if _gh_not_found(probe):
        user_probe = _run_gh(
            [
                "api",
                "-H",
                "Accept: application/vnd.github+json",
                f"users/{owner}/repos?per_page=1&page=1",
            ]
        )
        if user_probe.returncode == 0:
            print(
                f"Note: {owner!r} is not a GitHub Organization; listing repos as a user account.",
                file=sys.stderr,
            )
            return f"users/{owner}"
        print(user_probe.stderr or user_probe.stdout, file=sys.stderr)
        raise subprocess.CalledProcessError(
            user_probe.returncode,
            ["gh", "api", f"users/{owner}/repos"],
            user_probe.stdout,
            user_probe.stderr,
        )
    print(probe.stderr or probe.stdout, file=sys.stderr)
    raise subprocess.CalledProcessError(
        probe.returncode,
        ["gh", "api", f"orgs/{owner}/repos"],
        probe.stdout,
        probe.stderr,
    )


def list_owner_repo_names(owner: str) -> list[str]:
    """All repository names for this organization or user (paginated)."""
    base = _list_repos_api_path(owner)
    names: list[str] = []
    page = 1
    while True:
        proc = _run_gh(
            [
                "api",
                "-H",
                "Accept: application/vnd.github+json",
                f"{base}/repos?per_page=100&page={page}",
            ]
        )
        if proc.returncode != 0:
            print(proc.stderr, file=sys.stderr)
            raise subprocess.CalledProcessError(
                proc.returncode,
                ["gh", "api", f"{base}/repos"],
                proc.stdout,
                proc.stderr,
            )
        chunk = json.loads(proc.stdout) if proc.stdout.strip() else []
        if not chunk:
            break
        for item in chunk:
            if isinstance(item, dict) and "name" in item:
                names.append(item["name"])
        if len(chunk) < 100:
            break
        page += 1
    return names


def filter_benchmark_repos(
    repo_names: list[str], tool_slug: str, date: str | None
) -> list[str]:
    return sorted(
        n
        for n in repo_names
        if benchmark_repo_name_matches_tool(n, tool_slug, date)
    )


def delete_repo(org: str, repo_name: str) -> tuple[bool, str]:
    proc = _run_gh(["api", "-X", "DELETE", f"/repos/{org}/{repo_name}"])
    if proc.returncode == 0:
        return True, ""
    err = (proc.stderr or proc.stdout or "").strip()
    return False, err or f"exit {proc.returncode}"


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Delete benchmark repos matching step 0 naming (__tool_slug__YYYYMMDD). "
        "Default: dry-run (list only). Use --execute to delete.",
    )
    parser.add_argument(
        "--org",
        required=True,
        help="Owner: GitHub Organization slug **or** user login that owns the fork repos",
    )
    parser.add_argument(
        "--tool",
        required=True,
        help="Tool name / slug as passed to step 0 --name (e.g. neatcode_staging)",
    )
    parser.add_argument(
        "--date",
        metavar="YYYYMMDD",
        default=None,
        help="Only repos ending with this date segment (default: any date)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete matching repos (without this flag, only prints names)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON summary on stdout",
    )
    args = parser.parse_args()

    tool_slug = tool_slug_from_ai_name(args.tool)
    if args.date is not None and (len(args.date) != 8 or not args.date.isdigit()):
        parser.error("--date must be exactly 8 digits (YYYYMMDD)")

    owner = args.org
    try:
        all_names = list_owner_repo_names(owner)
    except subprocess.CalledProcessError as e:
        print(e.stderr or e, file=sys.stderr)
        sys.exit(1)

    candidates = filter_benchmark_repos(all_names, tool_slug, args.date)

    if args.json:
        payload = {
            "org": owner,
            "tool_slug": tool_slug,
            "date_filter": args.date,
            "dry_run": not args.execute,
            "candidates": candidates,
            "deleted": [],
            "errors": [],
        }
        if args.execute:
            for name in candidates:
                ok, err = delete_repo(owner, name)
                if ok:
                    payload["deleted"].append(name)
                else:
                    payload["errors"].append({"repo": name, "error": err})
        print(json.dumps(payload, indent=2))
        if args.execute and payload["errors"]:
            sys.exit(1)
        return

    if not candidates:
        print(f"No matching repos in {owner} for tool slug {tool_slug!r}", file=sys.stderr)
        return

    mode = "DELETE" if args.execute else "Would delete (dry-run)"
    print(f"{mode}: {len(candidates)} repo(s)")
    for name in candidates:
        print(f"  {owner}/{name}")

    if not args.execute:
        print("\nRe-run with --execute to delete these repositories.", file=sys.stderr)
        return

    errors: list[tuple[str, str]] = []
    for name in candidates:
        ok, err = delete_repo(owner, name)
        if not ok:
            errors.append((name, err))
            print(f"FAILED {owner}/{name}: {err}", file=sys.stderr)

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
