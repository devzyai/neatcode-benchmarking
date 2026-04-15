#!/usr/bin/env python3
"""
Print micro precision / recall / F1 for every tool in an evaluations.json.

Run from the offline/ directory:

  uv run python analysis/report_all_tools.py
  uv run python analysis/report_all_tools.py --evaluations results/gpt-4o/evaluations.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


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
    args = parser.parse_args()

    p = args.evaluations
    if not p.exists():
        raise SystemExit(f"File not found: {p.resolve()}")

    data = json.loads(p.read_text())
    by_tool: dict[str, dict[str, int]] = {}

    for _url, tools in data.items():
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

    print(f"Evaluations: {p.resolve()}")
    print(f"Golden PRs:  {len(data)}")
    print(f"Tools:       {len(rows)}")
    print()
    print(f"{'Tool':<24} {'PRs':>4} {'Prec':>8} {'Recall':>8} {'F1':>8}  {'TP':>4} {'FP':>5} {'FN':>4}")
    print("-" * 78)
    for r in rows:
        print(f"{r[0]:<24} {r[4]:4} {r[1]:7.1%} {r[2]:7.1%} {r[3]:7.1%}  {r[5]:4} {r[6]:5} {r[7]:4}")


if __name__ == "__main__":
    main()
