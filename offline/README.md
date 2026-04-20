# Offline Code Review Benchmark

Open replication of the code review benchmark used by companies like [Augment](https://www.augmentcode.com/blog/introducing-augment-code-review) and [Greptile](https://www.greptile.com/blog/code-review-benchmark). 40 PRs across four major open-source codebases with human-verified golden comments. An LLM judge evaluates each tool: does it find real issues? Does it generate noise?

## Evaluated tools

| Tool | Type |
|---|---|
| [Augment](https://www.augmentcode.com/) | AI code review |
| [Claude Code](https://claude.ai) | AI assistant |
| [CodeRabbit](https://www.coderabbit.ai/) | AI code review |
| [Codex](https://openai.com/codex) | AI assistant |
| [Cursor Bugbot](https://cursor.com) | AI code review |
| [Gemini](https://gemini.google.com/) | AI assistant |
| [GitHub Copilot](https://github.com/features/copilot) | AI code review |
| [Graphite](https://graphite.dev/) | AI code review |
| [Greptile](https://www.greptile.com/) | AI code review |
| [Propel](https://propelauth.com/) | AI code review |
| [Qodo](https://www.qodo.ai/) | AI code review |

Adding a new tool requires forking the benchmark PRs and collecting the tool's reviews — see Steps 0 and 1 below.

## Methodology

Each of the 40 benchmark PRs has a set of **golden comments**: real issues that a human reviewer identified, with severity labels (Low / Medium / High / Critical). These are the ground truth.

For each tool, the pipeline:
1. **Extracts** individual issues from the tool's review comments (line-specific comments become candidates directly; general comments are sent to an LLM to extract distinct issues)
2. **Deduplicates** candidates — tools that post the same issue in both a summary comment and as inline comments would otherwise be penalised for the duplicate. An LLM groups candidates that express the same underlying concern; sibling duplicates are not counted as false positives in step 3.
3. **Judges** each candidate against each golden comment using an LLM: "Do these describe the same underlying issue?"
4. **Computes** precision (what fraction of the tool's comments matched real issues?) and recall (what fraction of real issues did the tool find?)

The judge accepts semantic matches — different wording is fine as long as the underlying issue is the same.

### Judge models used

Results are stored per judge model so you can compare how different judges score:
- `anthropic_claude-opus-4-5-20251101`
- `anthropic_claude-sonnet-4-5-20250929`
- `openai_gpt-5.2`

## Known limitations

- **Static dataset** — PRs are from well-known repos; tools may have seen them during training (training data leakage). See [`online/`](../online/) for a benchmark that avoids this.
- **Golden comments are human-curated** but may miss edge cases or disagree with other reviewers.
- **LLM judge introduces model-dependent variance** — different judge models may score differently. We mitigate this by using consistent prompts and reporting the judge model used.

---

## Setup

1. Install dependencies:
```bash
cd offline
uv sync
```

2. Create `.env` file (see `.env.example`):
```bash
cp .env.example .env
# fill in your tokens
```

## Tests

Run the pytest suite (no network access required):

```bash
pytest
```

## Linting

```bash
ruff check .
```

## Grafana mini (5 PRs)

Checkout the branch your team shares, then **[`docs/LIMITED_BENCHMARK_GRAFANA_MINI.md`](docs/LIMITED_BENCHMARK_GRAFANA_MINI.md)** (short step list). Dataset notes: [`golden_grafana_only/README.md`](golden_grafana_only/README.md).

---

## Paths and reporting defaults

Judge outputs (steps 2–3) go under `results/<sanitized MARTIAN_MODEL>/` (slashes become underscores), e.g. `MARTIAN_MODEL=openai/gpt-5.2` → `results/openai_gpt-5.2/`.

- **`analysis/report_all_tools.py`** defaults to `results/openai_gpt-5.2/evaluations.json`. Use **`--subset-from-golden`** + **`--subset-limit`** or **`--subset-urls-file`** to aggregate micro metrics on a fixed list of golden PRs only (same PRs as a small step 0 run — useful for before/after comparisons without re-judging the full benchmark).
- **`analysis/report_scores_by_repo.py`** uses the same file when `MARTIAN_MODEL` is unset (`openai/gpt-5.2`). Override with `--evaluations` or set `MARTIAN_MODEL` in `.env` for other runs.
- **`analysis/merge_neatcode_into_openai_gpt52.py`** merges `neatcode` from `results/gpt-5.2/` into `results/openai_gpt-5.2/` by default; use `--neat-subdir` / `--openai-subdir` if your directory names differ from those judge outputs.

---

## Pipeline steps

All scripts live in the `code_review_benchmark/` package. Run from the `offline/` directory. Output goes to `results/`.

### 0. Fork PRs

Fork benchmark PRs into a GitHub org where the tool under evaluation is installed.
One bench repo is created **per golden JSON file** — all PRs from the same file
(regardless of the upstream `url` host) are pushed as separate branches into that
shared repo. Re-running on the same day reuses already-created repos.

#### Single-PR CLI

```bash
uv run python -m code_review_benchmark.step0_fork_prs \
    https://github.com/owner/repo/pull/123 --org <ORG> --name <TOOL>
```

#### Recommended: orchestrated batch run (3-stage pipeline)

```bash
uv run python -m code_review_benchmark.step0_orchestrate_forks \
    --org <ORG_NAME> --name <TOOL_NAME> --golden-dir golden_comments
```

The orchestrator runs three stages:

| Stage | What happens | Concurrency |
|-------|-------------|-------------|
| **1. Clone + Bootstrap** | Clones every unique upstream repo referenced by the golden URLs. Creates one bench repo per golden JSON file under your org (private -> disable actions -> make public). | Serial |
| **2. Prepare** | For each PR URL: fetches the PR head into the cached upstream clone, then pushes base + head branches to the bench repo via **refspec** (`git push <url> SHA:refs/heads/branch`). No `git checkout` — fully parallel-safe. | `--prepare-concurrency` (default 10) |
| **3. Open PRs** | Calls `POST /repos/{org}/{repo}/pulls` for each successfully prepared PR. | `--pr-open-concurrency` (default 10) |

**Flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--repos` | 5 | Golden JSON files to process |
| `--prs-per-repo` | 10 | PR URLs per file |
| `--prepare-concurrency` | 10 | Parallel fetch+push tasks (stage 2) |
| `--pr-open-concurrency` | 10 | Parallel GitHub API PR-open calls (stage 3) |
| `--bench-date` | (today) | `YYYYMMDD` suffix for bench repo name; reuse `grafana__TOOL__20260416` on a later day |
| `--upstream-clone-dir` | (none) | Parent dir for persistent `owner__repo` git clones; **reuse** across runs (no temp re-clone) |

**Examples:**

```bash
# Default: 5 repos x 10 PRs, 10 parallel prepares, 10 parallel opens
uv run python -m code_review_benchmark.step0_orchestrate_forks \
    --org my-org --name coderabbit

# Open all 50 PRs at once after preparing
uv run python -m code_review_benchmark.step0_orchestrate_forks \
    --org my-org --name coderabbit --pr-open-concurrency 50

# Faster prepare for many different upstreams
uv run python -m code_review_benchmark.step0_orchestrate_forks \
    --org my-org --name coderabbit --prepare-concurrency 20

# Grafana only, first 5 golden PRs (committed slice: golden_grafana_only/grafana.json;
# same URLs as analysis/subsets/grafana_first_5.urls). Steps 1–3 still use default golden_comments/.
./scripts/grafana_mini_fork.sh --org my-org --name neatcode

# Same, with safer defaults for flaky networks (persistent upstream clone, serial prepare/open):
./scripts/grafana_mini_fork_safe.sh --org my-org --name neatcode
```

See `golden_grafana_only/README.md` to regenerate that file after editing the first five PRs in `golden_comments/grafana.json`.

**After one of five Grafana PRs opened:** use `golden_grafana_remaining_four/` (four URLs, no re-clone per PR — one orchestrator run, one upstream clone) and `--bench-date` if today is no longer the repo’s date suffix. See `golden_grafana_remaining_four/README.md`.

**Bench repo names** (step 0 and step 1 share the same parsing):

| Shape | Pattern | Example |
|-------|---------|---------|
| Single-PR (legacy) | `{config}__{upstream_repo}__{tool}__PR{n}__{date}` | `cal_dot_com__repo__tool-x__PR12__20240101` |
| Shared multi-PR (legacy) | `{config}__{upstream_repo}__{tool}__{YYYYMMDD}` | four segments ending in `YYYYMMDD` |
| Shared multi-PR (current) | `{config}__{tool}__{YYYYMMDD}` | `sentry__coderabbit__20260407` |

**Head branches** opened in the bench repo: legacy `pr-{N}` (digits only) or current `pr-{owner}-{repo}-{N}` (upstream PR number is the trailing `-{N}`). Step 1 resolves golden comments by URL; for the three-part repo name it matches `golden_comments/{config}.json` plus PR number.

The command exits `0` when all stages succeed, `1` when any task fails.
The summary prints per-stage failure counts for easy triage.

### 1. Download PR data

Aggregate PR reviews from benchmark repos with golden comments.
Supports single-PR repos, legacy four-part shared repos, and three-part shared repos (see bench repo naming above). Multiple PRs in one repo are discovered from head branch names; `source_repo` in the output is taken from the golden PR URL when possible.

```bash
# Full run (incremental - skips already downloaded)
uv run python -m code_review_benchmark.step1_download_prs --output results/benchmark_data.json

# Test mode: 1 PR per tool
uv run python -m code_review_benchmark.step1_download_prs --output results/benchmark_data.json --test

# Force refetch all reviews
uv run python -m code_review_benchmark.step1_download_prs --output results/benchmark_data.json --force

# Force refetch for a specific tool
uv run python -m code_review_benchmark.step1_download_prs --output results/benchmark_data.json --force --tool copilot
```

**Output:** `results/benchmark_data.json`

### 2. Extract comments

Extract individual issues from review comments for matching:

```bash
# Extract for all tools
uv run python -m code_review_benchmark.step2_extract_comments

# Extract for specific tool
uv run python -m code_review_benchmark.step2_extract_comments --tool claude

# Limit extractions (for testing)
uv run python -m code_review_benchmark.step2_extract_comments --tool claude --limit 5
```

Line-specific comments become direct candidates. General comments are sent to the LLM to extract individual issues.

**Output:** Updates `results/benchmark_data.json` with `candidates` field per review.

### 2.5. Deduplicate candidates (recommended)

Group duplicate candidates before judging. Tools that post the same issue in
both a summary and inline comments would otherwise receive false positive
penalties for the duplicate. This step is optional but recommended — without it,
precision scores are artificially lowered for tools with overlapping comment
formats.

```bash
# Deduplicate all tools
uv run python -m code_review_benchmark.step2_5_dedup_candidates

# Deduplicate a specific tool only
uv run python -m code_review_benchmark.step2_5_dedup_candidates --tool qodo

# Force re-run (default is incremental)
uv run python -m code_review_benchmark.step2_5_dedup_candidates --force
```

**Output:** `results/{model}/dedup_groups.json`

Each entry maps `(golden_url, tool)` to a list of groups, where each group is a
list of candidate indices that express the same issue. Singletons (no duplicate)
appear as single-element groups.

### 3. Judge comments

Match candidates against golden comments, calculate precision/recall:

```bash
# Evaluate all tools (with dedup applied)
uv run python -m code_review_benchmark.step3_judge_comments \
  --dedup-groups results/{model}/dedup_groups.json

# Evaluate specific tool
uv run python -m code_review_benchmark.step3_judge_comments --tool claude

# Force re-evaluation
uv run python -m code_review_benchmark.step3_judge_comments --tool claude --force

# Run without dedup (baseline for comparison)
uv run python -m code_review_benchmark.step3_judge_comments \
  --evaluations-file results/{model}/evaluations_no_dedup.json
```

**Output:** `results/{model}/evaluations.json` with TP/FP/FN, precision, recall per review.

`--dedup-groups` — path to the dedup groups file from step 2.5. Duplicate
candidates in the same group will not be counted as false positives.

`--evaluations-file` — override the default output path, useful when running
multiple comparison variants without overwriting the baseline.

### 4. Generate dashboard

Regenerate the dashboard JSON and HTML from evaluation results:

```bash
uv run python analysis/benchmark_dashboard.py
```

**Output:** `analysis/benchmark_dashboard.json` and `analysis/benchmark_dashboard.html`

Open `analysis/benchmark_dashboard.html` in a browser to view results. Run this after adding new tools or re-running the judge to update the dashboard.

### Leaderboard and per-repo scores

After you have `results/openai_gpt-5.2/evaluations.json` (and optionally merged NeatCode with `results/gpt-5.2/`):

```bash
# Micro P/R/F1 for every tool (default path: openai_gpt-5.2)
uv run python analysis/report_all_tools.py

# Same leaderboard file, but only the first N PRs from a golden file (e.g. Grafana mini-slice)
uv run python analysis/report_all_tools.py \
  --subset-from-golden golden_comments/grafana.json --subset-limit 5

# Or a fixed URL list (see analysis/subsets/grafana_first_5.urls)
uv run python analysis/report_all_tools.py \
  --subset-urls-file analysis/subsets/grafana_first_5.urls

# Point at a merged evaluations.json from another clone (historical baseline)
uv run python analysis/report_all_tools.py \
  --evaluations /path/to/code-review-benchmark/offline/results/openai_gpt-5.2/evaluations.json \
  --subset-from-golden golden_comments/grafana.json --subset-limit 5

# Same metrics for one upstream product (keycloak | cal | grafana | sentry)
uv run python analysis/report_scores_by_repo.py --repo keycloak --tool neatcode
```

**Workflow:** use **`--subset-*`** on the **previous** merged `evaluations.json` to record neatcode vs competitors on exactly the PRs you will re-fork. After step 0–3 on a new tool build, merge neatcode into `evaluations.json` and run the same command again to decide whether the new approach beats the old slice and how it ranks vs others.

To copy **neatcode** evaluations/candidates from `results/gpt-5.2/` into the merged OpenAI leaderboard file (both dirs must exist):

```bash
uv run python analysis/merge_neatcode_into_openai_gpt52.py
```

### 5. Summary table

Show review counts by tool and repo:

```bash
uv run python -m code_review_benchmark.summary_table
```

**Example output:**
```
Tool        cal_dot_com  grafana      keycloak     sentry       Total
----------------------------------------------------------------------
claude      10           10           10           10           40
coderabbit  10           10           10           10           40
...
```

### 6. Export by tool

Export tool reviews with evaluation results:

```bash
# Export Claude (default)
uv run python -m code_review_benchmark.step4_export_by_tool

# Export specific tool
uv run python -m code_review_benchmark.step4_export_by_tool --tool greptile
```

**Output:** `results/{tool}_reviews.xlsx`

---

## GitHub Actions

Benchmark automation is split into two workflows so fork setup does not require judge (Martian) secrets:

| Workflow | File | Purpose |
|----------|------|---------|
| **Benchmark fork (step 0)** | [`.github/workflows/benchmark-fork.yml`](../.github/workflows/benchmark-fork.yml) | Orchestrate forks: create repos and open PRs in `benchmark_org`. |
| **Benchmark evaluate (steps 1–3)** | [`.github/workflows/benchmark-evaluate.yml`](../.github/workflows/benchmark-evaluate.yml) | Download reviews → extract → dedup → judge. Uploads `offline/results/` as an artifact. |
| **Benchmark delete repos** | [`.github/workflows/benchmark-delete-repos.yml`](../.github/workflows/benchmark-delete-repos.yml) | Optional: list or delete fork repos matching step 0 naming (**list** by default; choose **delete** to remove). |

**Typical order:** run **Benchmark fork** first (or use existing fork repos), then **Benchmark evaluate** when PRs are ready. Both use `workflow_dispatch` only (Actions tab → select workflow → Run workflow).

### Benchmark fork (`benchmark-fork.yml`)

**Secrets:** `BENCHMARK_GH_TOKEN` only. Martian variables are **not** required.

**Inputs:** `ref`, `benchmark_org`, `tool` (same meanings as below).

### Benchmark evaluate (`benchmark-evaluate.yml`)

**Secrets:** `BENCHMARK_GH_TOKEN`, `MARTIAN_API_KEY`, and `MARTIAN_MODEL` (or pass `judge_model`).

**Workflow inputs**

| Input | Meaning |
|-------|---------|
| `ref` | Git branch or tag of **this** (`neatcode-benchmarking`) repo to checkout. Use this to run a specific version of the benchmark scripts. Default: `main`. |
| `benchmark_org` | GitHub organization slug where benchmark fork repos live (e.g. a dedicated eval org). Passed to `--org` for step 1. |
| `tool` | Tool slug matching step 0 `--name` and repo name segments (e.g. `neatcode_staging`). |
| `step1_force` | If true, passes `--force` to step 1 (refetch reviews). |
| `step1_test` | If true, passes `--test` to step 1 (one repo per tool). |
| `judge_model` | Optional. If set, overrides `MARTIAN_MODEL` for the judge. If empty, the `MARTIAN_MODEL` repository secret is used. |
| `limit` | Optional. If non-empty, passed as `--limit` to steps 2 and 3 for smoke runs. |

**Repository secrets (Settings → Secrets and variables → Actions)**

| Secret | Required | Purpose |
|--------|----------|---------|
| `BENCHMARK_GH_TOKEN` | Yes (fork, evaluate, delete workflows) | Personal access token (classic or fine-grained) used as `GH_TOKEN` / `GITHUB_TOKEN` for `gh`. Must be able to **list and read** PRs in `benchmark_org`, **create repositories** there for step 0, and **delete repositories** there if you use the delete script or workflow. The default `GITHUB_TOKEN` in Actions cannot replace this for arbitrary orgs. |
| `MARTIAN_API_KEY` | Yes (evaluate workflow only) | API key for the OpenAI-compatible judge endpoint. |
| `MARTIAN_MODEL` | Yes for evaluate (unless you always pass `judge_model`) | Default judge model id (e.g. `openai/gpt-5.2`). Same value as in local `.env`. |

Optional: add `MARTIAN_BASE_URL` only if you use a non-default judge endpoint; for a custom base URL you can extend the workflow `env` or rely on local `.env` when running manually.

### Deleting benchmark repos

Bench repo names follow step 0 (see [bench naming](#paths-and-reporting-defaults) above): they end with `__{tool_slug}__{YYYYMMDD}`. The **`--org`** argument is the **account that owns the forks**: a GitHub **Organization** slug, or a **user** login if the forks live under a personal account (the script lists via the org API first, then falls back to the user API if the name is not an org).

The script uses the **`gh` CLI** (same as other steps). **GitHub-hosted runners** (`ubuntu-latest`) already include `gh`; you do not install it in the workflow. Locally, install [GitHub CLI](https://cli.github.com/) or rely on `GH_TOKEN` with a `gh` binary.

To remove repos from that account after a run:

```bash
cd offline
# Dry-run: lists matching repos (default — no deletes)
uv run python -m code_review_benchmark.delete_benchmark_repos --org YOUR_ORG --tool YOUR_TOOL_NAME

# Only repos for a single day
uv run python -m code_review_benchmark.delete_benchmark_repos --org YOUR_ORG --tool YOUR_TOOL_NAME --date 20260401

# Actually delete (irreversible)
uv run python -m code_review_benchmark.delete_benchmark_repos --org YOUR_ORG --tool YOUR_TOOL_NAME --execute
```

The GitHub Actions workflow **Benchmark delete repos** runs the same CLI. Use the **`action`** input: **`list`** (default) prints matches only; choose **`delete`** to pass **`--execute`** and remove repos (irreversible). A boolean checkbox was unreliable in bash, so this workflow uses an explicit **`list` / `delete`** choice instead.

**PAT:** deleting repositories requires **`BENCHMARK_GH_TOKEN`** to include **administration: delete repositories** (or equivalent classic scope) on `benchmark_org`. Fine-grained PATs must allow repository deletion for that org.

**PAT permissions (typical)**

- **Step 1 only:** read access to repositories in `benchmark_org` (metadata, pull requests, contents as needed by `gh`).
- **Step 0 (orchestrate):** additionally **create** repositories (and admin as required by your org policy) in `benchmark_org`.

Scope the token to the **benchmark organization** when using fine-grained PATs.

**Scripts ref vs NeatCode backend**

- The workflow **`ref` / branch** selects which **commit of these benchmark scripts** runs (step 1–3 code, golden files, etc.).
- It does **not** select which version of **NeatCode** reviews the PRs. Review behavior is determined by the **GitHub App** installation on `benchmark_org` and the **webhook URL** configured for that app (e.g. staging or an experimental deployment). To compare backend changes, deploy the desired build and ensure the benchmark app’s webhook points at it before re-running reviews and step 1 with `step1_force` where appropriate.

---

## Data format

### Golden comments (`golden_comments/*.json`)

```json
[
  {
    "pr_title": "Fix race condition in worker pool",
    "url": "https://github.com/getsentry/sentry/pull/93824",
    "comments": [
      {
        "comment": "This lock acquisition can deadlock if the worker is interrupted between acquiring lock A and lock B",
        "severity": "High"
      }
    ]
  }
]
```

Source files: `sentry.json`, `grafana.json`, `keycloak.json`, `cal_dot_com.json`

### benchmark_data.json

```json
{
  "https://github.com/getsentry/sentry/pull/93824": {
    "pr_title": "...",
    "original_url": "...",
    "source_repo": "sentry",
    "golden_comments": [
      {"comment": "...", "severity": "High"}
    ],
    "reviews": [
      {
        "tool": "claude",
        "pr_url": "https://github.com/code-review-benchmark/...",
        "review_comments": [
          {"path": "...", "line": 42, "body": "...", "created_at": "..."}
        ],
        "candidates": ["issue description 1", "issue description 2"]
      }
    ]
  }
}
```

### evaluations.json

```json
{
  "https://github.com/getsentry/sentry/pull/93824": {
    "claude": {
      "precision": 0.75,
      "recall": 0.6,
      "true_positives": 3,
      "false_positives": 1,
      "false_negatives": 2,
      "matches": ["..."],
      "false_negatives_detail": ["..."]
    }
  }
}
```
