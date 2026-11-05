# weekly-kpi-report-agent

Weekly sales KPI report where every number is computed in code, the LLM only writes the narrative around the given figures, and a checker rejects any number in the text that is not in the computed set.

**The team task it replaces:** every Monday someone pulls last week's sales numbers into a summary email (revenue, orders, average order value, top products, what changed), and sometimes a hand-typed figure is wrong. This tool writes that email as a **Gmail draft**. A human reads it and presses send. The code has no send path.

## How it works

```
xlsx ──► clean (dedupe, cancellations, adjustments, non-product codes, price ≤ 0)
     ──► 42 figures for the ISO week, computed in pandas, each with a display string + source
     ──► Claude (claude-sonnet-5-5) writes headline + paragraphs, copying figure strings with [Fn] markers
     ──► number checker: every number must equal the display of the figure its [Fn] points to,
         and rose/fell-type words must match the sign of a change figure
     ──► pass → report.md / report.html / figures.json + Gmail draft
         fail → retry with the checker's feedback (max 3 attempts), then a figures-only draft titled
                "[NEEDS REVIEW]" with the rejected sentences quoted
```

- **Figures** (F1–F42): revenue, orders, AOV, units, customers, new vs returning, cancellation rate. Each one is compared with the previous week, the 4-week average and the same ISO week a year earlier. Also the top 5 products and countries, and data-quality counts. Every figure carries its source: the formula, the line count, the date range and the file.
- **Checker** (`checker.py`): finds every number in the text. It fails a number with no `[Fn]` marker (`missing_reference`), a number that belongs to a different figure (`wrong_reference`), and a number that isn't in the set at all (`unknown_number`). It also fails a direction word that contradicts the sign of a change figure (`wrong_direction`). Product and country names in double quotes are exempt, so "REGENCY CAKESTAND 3 TIER" is not read as the number 3.
- **Statuses**: `ok`, `needs_review` (with reasons), `no_data`. Exit codes 0 / 2 / 3, so a scheduled run is visibly non-zero when a human has to look.
- **Failure paths, each one tested**:
  - narrative fails the check 3 times
  - model reply isn't valid JSON
  - provider error (only the error type is kept, never the message)
  - week with no sales
  - partial week (data stops before Sunday)
  - per-run cost cap (`KPI_COST_CAP_USD`, default $5)
  - Gmail draft fails (the local report is still written)
- **Untrusted text**: product descriptions come from the data. They reach the model only inside one `<user_input>` block, cut to 100 characters, with `<` and `>` escaped. The system prompt is a constant. Model output is parsed by a Pydantic schema and then checked.

## Measured

`weekly-kpi-report eval-checker` builds a labelled set from real week figures. Narratives are generated in code: 60 clean ones and 60 with exactly one planted error, 10 of each type (`digit_swap`, `rounding`, `sign_flip`, `misattributed`, `invented`, `wrong_direction`). On the full dataset (weeks 2010-12-06..2011-11-28, seed 7) the result is **precision 1.000, recall 1.000 on 120 cases**. Seeds 1–5 give the same result.

The planted errors are synthetic and the checker is exact matching by design, so this number shows the checker does what it claims on those six error kinds. It says nothing about how often the LLM writes a clean narrative on its first try; the backfill summary (`backfill_summary.csv`, column `attempts`) records that.

What the checker does **not** check: wording outside the closed direction-word list ("best week ever", "slightly", "surged"), wrong product or country names, claims without numbers, and spelled-out numbers ("five").

## Run it

```bash
uv sync
uv run weekly-kpi-report download                       # data/raw/online_retail_II.xlsx, SHA-256 checked
uv run weekly-kpi-report eval-checker --data data/raw/online_retail_II.xlsx --from 2010-12-06 --to 2011-11-28 --out out/eval
export ANTHROPIC_API_KEY=...                            # never committed
uv run weekly-kpi-report backfill --data data/raw/online_retail_II.xlsx --from 2010-12-06 --to 2011-12-05 --out out/backfill
uv run weekly-kpi-report auth                           # Gmail OAuth, scope gmail.compose only
uv run weekly-kpi-report run --data data/raw/online_retail_II.xlsx --as-of 2011-09-26   # draft for week 2011-09-19
```

`run --no-gmail` writes only the local `out/<week>/report.md|html|figures.json`. Backfill never touches Gmail.

| Env var | Default |
| --- | --- |
| `ANTHROPIC_API_KEY` | (required for narratives) |
| `KPI_COST_CAP_USD` | `5.0` per run |
| `KPI_REPORT_TO` | `modis0001@gmail.com` (demo inbox) |
| `GOOGLE_OAUTH_CLIENT_FILE` | `~/.config/portfolio-demos/client_secret.json` |
| `KPI_GMAIL_TOKEN_FILE` | `~/.config/portfolio-demos/token-weekly-kpi-report.json` |

Schedule examples, which the code doesn't install: `deploy/com.portfolio.weekly-kpi-report.plist` (launchd, Mondays 07:00) and `deploy/crontab.example`.

## Development

`make check` (ruff, mypy strict, security scans, unit tests) · `make test` · acceptance tests: `uv run pytest tests/acceptance`. The spec with all acceptance criteria is `specs/weekly-kpi-report.md`. All external services (Anthropic, Gmail, the download) are mocked in tests.

## Data

Data: Online Retail II (Chen, D., 2012), UCI Machine Learning Repository, https://doi.org/10.24432/C5CG6D — licensed CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).

The raw file is downloaded by a script and is not committed. Customer ids are numeric pseudonyms in the source and never appear in any output.
