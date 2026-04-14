#!/usr/bin/env python3
"""
Report micro precision / recall / F1 for one upstream repo from evaluations.json.

Run from the offline/ directory (same as other benchmark steps):

  uv run python analysis/report_scores_by_repo.py --repo keycloak
  uv run python analysis/report_scores_by_repo.py --repo cal --tool neatcode
  uv run python analysis/report_scores_by_repo.py --repo grafana \\
      --evaluations results/gpt-4o/evaluations.json
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def load_dotenv_cwd() -> None:
    env_path = Path(".env")
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def default_evaluations_path() -> Path:
    load_dotenv_cwd()
    model = os.environ.get("MARTIAN_MODEL", "gpt-4o")
    safe = model.strip().replace("/", "_")
    return Path("results") / safe / "evaluations.json"


# Golden PR URLs in benchmark_data are github.com/{owner}/{repo}/pull/{n}
REPO_MATCHERS: dict[str, tuple[str, ...]] = {
    "keycloak": ("/keycloak/keycloak/pull/",),
    "cal": ("/calcom/cal.com/pull/",),
    "grafana": ("/grafana/grafana/pull/",),
    "sentry": ("/getsentry/sentry/pull/",),
}

REPO_ALIASES: dict[str, str] = {
    "cal.com": "cal",
    "calcom": "cal",
    "cal_dot_com": "cal",
    "keycloak": "keycloak",
    "grafana": "grafana",
    "sentry": "sentry",
}


def normalize_repo(name: str) -> str:
    key = name.strip().lower()
    if key in REPO_ALIASES:
        return REPO_ALIASES[key]
    if key in REPO_MATCHERS:
        return key
    raise ValueError(
        f"Unknown repo {name!r}. Use one of: {', '.join(sorted(REPO_MATCHERS))} "
        f"(cal aliases: cal.com, cal_dot_com, calcom)"
    )


def golden_url_in_repo(golden_url: str, canonical: str) -> bool:
    for fragment in REPO_MATCHERS[canonical]:
        if fragment in golden_url:
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate precision/recall/F1 for one upstream repo from evaluations.json",
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="Upstream bucket: keycloak | cal | grafana | sentry (see cal aliases in --help)",
    )
    parser.add_argument(
        "--tool",
        default="neatcode",
        help="Tool name as stored in evaluations (default: neatcode)",
    )
    parser.add_argument(
        "--evaluations",
        type=Path,
        default=None,
        help="Path to evaluations.json (default: results/<MARTIAN_MODEL>/evaluations.json)",
    )
    args = parser.parse_args()

    try:
        canonical = normalize_repo(args.repo)
    except ValueError as e:
        parser.error(str(e))

    eval_path = args.evaluations if args.evaluations is not None else default_evaluations_path()
    if not eval_path.exists():
        raise SystemExit(f"Evaluations file not found: {eval_path.resolve()}")

    with open(eval_path) as f:
        data: dict = json.load(f)

    tool = args.tool
    tp = fp = fn = 0
    n_reviews = 0

    for golden_url, tools in data.items():
        if not golden_url_in_repo(golden_url, canonical):
            continue
        result = tools.get(tool)
        if not result or result.get("skipped"):
            continue
        tp += int(result.get("tp", 0))
        fp += int(result.get("fp", 0))
        fn += int(result.get("fn", 0))
        n_reviews += 1

    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0

    print(f"Evaluations: {eval_path}")
    print(f"Repo filter: {canonical} ({REPO_MATCHERS[canonical][0]}…)")
    print(f"Tool:        {tool}")
    print(f"Reviews:     {n_reviews}")
    print(f"TP / FP / FN: {tp} / {fp} / {fn}")
    print(f"Precision:   {prec:.1%}")
    print(f"Recall:      {rec:.1%}")
    print(f"F1:          {f1:.1%}")


if __name__ == "__main__":
    main()
