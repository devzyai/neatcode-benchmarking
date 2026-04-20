# Grafana mini dataset (first 5 golden PRs)

`grafana.json` here contains only the **first five** PRs from `golden_comments/grafana.json`, in the same order as `analysis/subsets/grafana_first_5.urls`.

**Quick steps:** shared branch + **[`docs/LIMITED_BENCHMARK_GRAFANA_MINI.md`](../docs/LIMITED_BENCHMARK_GRAFANA_MINI.md)**.

## Step 0 (fork five mirror PRs)

From `offline/`:

**Recommended (persistent upstream clone + serial prepare/open — fewer timeouts):**

```bash
./scripts/grafana_mini_fork_safe.sh --org <ORG> --name <TOOL>
```

**Maximum throughput (default orchestrator concurrency):**

```bash
./scripts/grafana_mini_fork.sh --org <ORG> --name <TOOL>
```

Same flags as step 0, without typing the Python module path. Equivalent:

`uv run python -m code_review_benchmark.step0_orchestrate_forks --org <ORG> --name <TOOL> --golden-dir golden_grafana_only --repos 1 --prs-per-repo 5`

Creates a single bench repo `grafana__<tool>__<YYYYMMDD>` with five branches / PRs.

## Steps 1–3 (download → judge)

Keep the default **`golden_comments/`** tree (full four products). Step 1’s `--golden` defaults to `golden_comments`; golden lookup for these five URLs matches `golden_comments/grafana.json`, same as the main benchmark.

## Regenerate after editing the main Grafana golden

If you change the first five entries in `golden_comments/grafana.json`, refresh this file from `offline/`:

```bash
python3 -c "import json, pathlib; s=pathlib.Path('golden_comments/grafana.json'); d=json.loads(s.read_text()); pathlib.Path('golden_grafana_only/grafana.json').write_text(json.dumps(d[:5], indent=2)+'\n')"
```
