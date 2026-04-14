#!/usr/bin/env python3
"""
Overlay `neatcode` from results/gpt-5.2/ into results/openai_gpt-5.2/ for
evaluations.json and candidates.json (same golden PR URLs).

Run from offline/:

  uv run python analysis/merge_neatcode_into_openai_gpt52.py
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge neatcode from gpt-5.2 into openai_gpt-5.2")
    parser.add_argument(
        "--results",
        type=Path,
        default=Path("results"),
        help="Results root (default: results)",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not write .bak copies before overwriting",
    )
    args = parser.parse_args()

    results = args.results.resolve()
    neat_dir = results / "gpt-5.2"
    openai_dir = results / "openai_gpt-5.2"

    neat_eval = neat_dir / "evaluations.json"
    neat_cand = neat_dir / "candidates.json"
    oa_eval = openai_dir / "evaluations.json"
    oa_cand = openai_dir / "candidates.json"

    for p in (neat_eval, neat_cand, oa_eval, oa_cand):
        if not p.exists():
            raise SystemExit(f"Missing required file: {p}")

    merged_eval = json.loads(oa_eval.read_text())
    neat_eval_data = json.loads(neat_eval.read_text())

    missing = [u for u in neat_eval_data if u not in merged_eval]
    if missing:
        raise SystemExit(f"{len(missing)} neat evaluation URL(s) missing from openai file: {missing[:3]}...")

    for url, tools in neat_eval_data.items():
        if "neatcode" not in tools:
            raise SystemExit(f"No neatcode key for {url}")
        merged_eval[url]["neatcode"] = tools["neatcode"]

    merged_cand = json.loads(oa_cand.read_text())
    neat_cand_data = json.loads(neat_cand.read_text())

    missing_c = [u for u in neat_cand_data if u not in merged_cand]
    if missing_c:
        raise SystemExit(f"{len(missing_c)} neat candidate URL(s) missing from openai candidates")

    for url, tools in neat_cand_data.items():
        if "neatcode" not in tools:
            raise SystemExit(f"No neatcode candidates for {url}")
        merged_cand[url]["neatcode"] = tools["neatcode"]

    if not args.no_backup:
        shutil.copy2(oa_eval, oa_eval.with_suffix(".json.bak"))
        shutil.copy2(oa_cand, oa_cand.with_suffix(".json.bak"))

    oa_eval.write_text(json.dumps(merged_eval, indent=2) + "\n")
    oa_cand.write_text(json.dumps(merged_cand, indent=2) + "\n")

    print(f"Merged neatcode into {oa_eval}")
    print(f"Merged neatcode into {oa_cand}")
    if not args.no_backup:
        print(f"Backups: {oa_eval.with_suffix('.json.bak')}, {oa_cand.with_suffix('.json.bak')}")


if __name__ == "__main__":
    main()
