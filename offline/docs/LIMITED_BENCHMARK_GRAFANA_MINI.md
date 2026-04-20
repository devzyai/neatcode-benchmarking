# Grafana mini benchmark (5 PRs)

Only **`neatcode-benchmarking`** is required. Work in **`offline/`**.

## 1. Repo + branch

```bash
cd neatcode-benchmarking
git fetch origin workflow/benchmarking
git checkout workflow/benchmarking
cd offline
uv sync
cp .env.example .env
```

Fill `.env`: `GITHUB_TOKEN`, `GH_TOKEN`, `MARTIAN_API_KEY`, `MARTIAN_BASE_URL`, `MARTIAN_MODEL`.  
Steps 2–3 write under `results/<dir>/` where `<dir>` is `MARTIAN_MODEL` with `/` → `_`. Examples: `MARTIAN_MODEL=gpt-5.2` → `results/gpt-5.2/`; `MARTIAN_MODEL=openai/gpt-5.2` → `results/openai_gpt-5.2/`.

## 2. Step 0 — create 5 mirror PRs

```bash
./scripts/grafana_mini_fork_safe.sh --org <ORG> --name <TOOL_SLUG>
```

`--org`: GitHub org for the bench repo; `--name`: tool slug used in the bench repo name (e.g. `neatcode-experimental`).

Wait until the review tool finishes on **all five** PRs.

- Retry / different day, same bench repo: add `--bench-date YYYYMMDD` (match the repo name you already have).
- Step 0 failed partway: see `golden_grafana_remaining_four/README.md`.

## 3. Download → extract → dedup → judge

Replace `<TOOL_SLUG>` and `<MODEL_DIR>` to match your `.env` (e.g. `gpt-5.2` → `gpt-5.2`, or `openai/gpt-5.2` → `openai_gpt-5.2`).

```bash
uv run python -m code_review_benchmark.step1_download_prs --output results/benchmark_data.json
uv run python -m code_review_benchmark.step2_extract_comments --tool <TOOL_SLUG>
uv run python -m code_review_benchmark.step2_5_dedup_candidates --tool <TOOL_SLUG>
uv run python -m code_review_benchmark.step3_judge_comments --tool <TOOL_SLUG> \
  --dedup-groups results/<MODEL_DIR>/dedup_groups.json
```

## 4. Report (5 PRs only)

```bash
uv run python analysis/report_all_tools.py \
  --evaluations results/<MODEL_DIR>/evaluations.json \
  --subset-urls-file analysis/subsets/grafana_first_5.urls
```

More detail: `README.md` in this folder.
