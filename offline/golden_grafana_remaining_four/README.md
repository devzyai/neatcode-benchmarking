# Remaining four Grafana PRs (mini set minus #76186)

Use this after **one** mirror PR already exists in `grafana__<tool>__<YYYYMMDD>` (e.g. 76186 opened first) and the other four failed during prepare (e.g. HTTP 408).

**One process → one upstream clone → four prepares** (use low concurrency for stability):

```bash
uv run python -m code_review_benchmark.step0_orchestrate_forks \
  --org devzy-benchmark --name neatcode-experimental \
  --golden-dir golden_grafana_remaining_four --repos 1 --prs-per-repo 4 \
  --prepare-concurrency 1 --pr-open-concurrency 1 \
  --bench-date 20260416 \
  --upstream-clone-dir ./upstream_clone
```

`--upstream-clone-dir ./upstream_clone` keeps Grafana under `offline/upstream_clone/grafana__grafana/` so **later runs reuse it** (no full re-clone each time). Add the same flag to one-off `step0_fork_prs` commands.

Replace `--bench-date` with the **suffix in your bench repo name** (`grafana__neatcode-experimental__**20260416**`). If you run on the **same calendar day** as that suffix, you can omit `--bench-date`.

Regenerate `grafana.json` from `golden_comments/grafana.json` if the first-five list changes:

```bash
python3 -c "
import json, pathlib
full = json.loads(pathlib.Path('golden_comments/grafana.json').read_text())
first5, rem = full[:5], [x for x in full[:5] if '76186' not in x.get('url','')]
pathlib.Path('golden_grafana_remaining_four/grafana.json').write_text(json.dumps(rem, indent=2)+chr(10))
"
```

Run from `offline/`.
