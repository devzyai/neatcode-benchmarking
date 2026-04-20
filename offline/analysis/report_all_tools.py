#!/usr/bin/env python3
"""
Print micro precision / recall / F1 for every tool in an evaluations.json.

Run from the offline/ directory:

  uv run python analysis/report_all_tools.py
  uv run python analysis/report_all_tools.py --evaluations results/gpt-4o/evaluations.json

Subset the same golden PRs you will fork in step 0 (compare historical leaderboard
without re-running the full benchmark):

  uv run python analysis/report_all_tools.py \\
    --evaluations results/openai_gpt-5.2/evaluations.json \\
    --subset-from-golden golden_comments/grafana.json --subset-limit 5

  uv run python analysis/report_all_tools.py \\
    --evaluations /path/to/other-repo/offline/results/openai_gpt-5.2/evaluations.json \\
    --subset-urls-file analysis/subsets/grafana_first_5.urls
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_subset_urls(args: argparse.Namespace) -> tuple[set[str] | None, list[str]]:
    """Return (url set or None for full file, ordered url list for display)."""
    if args.subset_urls_file:
        raw = Path(args.subset_urls_file).read_text().splitlines()
        ordered = [ln.strip() for ln in raw if ln.strip() and not ln.strip().startswith("#")]
        return set(ordered), ordered
    if args.subset_from_golden:
        path = Path(args.subset_from_golden)
        if not path.exists():
            raise SystemExit(f"Golden file not found: {path.resolve()}")
        arr = json.loads(path.read_text())
        if not isinstance(arr, list):
            raise SystemExit("Golden JSON must be a list of objects with 'url'")
        n = args.subset_limit
        if n is None or n < 1:
            raise SystemExit("--subset-from-golden requires --subset-limit >= 1")
        ordered = [str(item["url"]) for item in arr[:n] if isinstance(item, dict) and item.get("url")]
        return set(ordered), ordered
    if args.subset_limit is not None:
        raise SystemExit("Use --subset-from-golden with --subset-limit, or --subset-urls-file")
    return None, []


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate benchmark metrics per tool from evaluations.json",
    )
    parser.add_argument(
        "--evaluations",
        type=Path,
        default=Path("results/openai_gpt-5.2/evaluations.json"),
        help="Path to evaluations.json (default: merged leaderboard path)",
    )
    parser.add_argument(
        "--sort",
        choices=("f1", "precision", "recall", "tool"),
        default="f1",
        help="Sort column (default: f1 descending; tool = alphabetical)",
    )
    parser.add_argument(
        "--subset-from-golden",
        type=Path,
        default=None,
        help="Golden comments JSON (list); use with --subset-limit",
    )
    parser.add_argument(
        "--subset-limit",
        type=int,
        default=None,
        help="First N PRs from the golden list (order preserved in that file)",
    )
    parser.add_argument(
        "--subset-urls-file",
        type=Path,
        default=None,
        help="One golden PR URL per line (lines starting with # ignored)",
    )
    args = parser.parse_args()

    p = args.evaluations
    if not p.exists():
        raise SystemExit(f"File not found: {p.resolve()}")

    url_filter, ordered_subset = _load_subset_urls(args)

    data = json.loads(p.read_text())
    if url_filter is not None:
        missing = [u for u in ordered_subset if u not in data]
        if missing:
            print(
                "Warning: these subset URLs are missing from evaluations (skipped):",
                file=sys.stderr,
            )
            for u in missing:
                print(f"  {u}", file=sys.stderr)
    by_tool: dict[str, dict[str, int]] = {}

    for _url, tools in data.items():
        if url_filter is not None and _url not in url_filter:
            continue
        for tool, ev in tools.items():
            if ev.get("skipped"):
                continue
            m = by_tool.setdefault(tool, {"tp": 0, "fp": 0, "fn": 0, "n": 0})
            m["tp"] += int(ev.get("tp", 0))
            m["fp"] += int(ev.get("fp", 0))
            m["fn"] += int(ev.get("fn", 0))
            m["n"] += 1

    rows: list[tuple[str, float, float, float, int, int, int, int]] = []
    for t, m in by_tool.items():
        tp, fp, fn = m["tp"], m["fp"], m["fn"]
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        rows.append((t, prec, rec, f1, m["n"], tp, fp, fn))

    if args.sort == "f1":
        rows.sort(key=lambda r: (-r[3], r[0]))
    elif args.sort == "precision":
        rows.sort(key=lambda r: (-r[1], r[0]))
    elif args.sort == "recall":
        rows.sort(key=lambda r: (-r[2], r[0]))
    else:
        rows.sort(key=lambda r: r[0])

    n_golden = len(data) if url_filter is None else sum(1 for u in data if u in url_filter)
    print(f"Evaluations: {p.resolve()}")
    if url_filter is not None:
        print(f"Subset:      {len(ordered_subset)} URL(s) (filter active)")
    print(f"Golden PRs:  {n_golden}")
    print(f"Tools:       {len(rows)}")
    print()
    print(f"{'Tool':<24} {'PRs':>4} {'Prec':>8} {'Recall':>8} {'F1':>8}  {'TP':>4} {'FP':>5} {'FN':>4}")
    print("-" * 78)
    for r in rows:
        print(f"{r[0]:<24} {r[4]:4} {r[1]:7.1%} {r[2]:7.1%} {r[3]:7.1%}  {r[5]:4} {r[6]:5} {r[7]:4}")


if __name__ == "__main__":
    main()
