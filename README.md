# weekly-kpi-report-agent

Weekly sales KPI report where every number is computed in code, the LLM only writes the narrative around the given figures, and a checker rejects any number in the text that is not in the computed set.

**The team task it replaces:** every Monday someone pulls last week's sales numbers into a summary email (revenue, orders, average order value, top products, what changed), and sometimes a hand-typed figure is wrong. This tool writes that email as a **Gmail draft**. A human reads it and presses send. The code has no send path.

## How it works

```
xlsx ──► clean (dedupe, cancellations, adjustments, non-product codes, price ≤ 0)
     ──► 44 figures for the ISO week, computed in pandas, each with a display string + source
     ──► Claude (claude-sonnet-5-5) writes headline + paragraphs, copying figure strings with [Fn] markers
     ──► number checker: every number must equal the display of the figure its [Fn] points to,
         and rose/fell-type words must match the sign of a change figure
     ──► pass → report.md / report.html / figures.json + Gmail draft
         fail → retry with the checker's feedback (max 3 attempts), then a figures-only draft titled
                "[NEEDS REVIEW]" with the rejected sentences quoted
```

- **Figures** (F1–F44): revenue, orders, AOV, units, customers, new vs returning, cancellation rate. Each one is compared with the previous week, the 4-week average and the same ISO week a year earlier. Also the top 5 products and countries, and data-quality counts. Every figure carries its source: the formula, the line count, the date range and the file.
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
  - large cancellations: cancelled product value ≥ 25% of revenue (revenue counts orders before cancellations, so a big order cancelled the same week would otherwise look like a sales jump)
- **Numbers**: thousands are separated by a narrow no-break space (`£328 713`), never a comma, so they can't be misread as decimals; decimals use a point (`£950.34`, `14.3%`). The checker accepts exactly that form and rejects a comma-grouped or split number.
- **The report** (`report.html`, also the Gmail draft body): email-safe HTML in a dark charcoal-to-forest look with cream text and one amber accent, inline styles only, no images or external resources, a solid dark `bgcolor` on every content cell so it stays readable where gradients are stripped. A "Needs review" banner in plain words when something is off, then the headline, four key numbers with the change vs last week, the narrative with small source markers, "Worth a look", top products and countries, and the sources and all figures folded away at the bottom.
- **Untrusted text**: product descriptions come from the data. They reach the model only inside one `<week-data-…>` block whose tag ends in 16 random hex characters, new on every message (so a description can't forge the closing tag), cut to 100 characters, with `<` and `>` escaped. The system prompt is a constant. Model output is parsed by a Pydantic schema and then checked.

## Measured

`weekly-kpi-report eval-checker` builds a labelled set from real week figures. Narratives are generated in code: 60 clean ones and 60 with exactly one planted error, 10 of each type (`digit_swap`, `rounding`, `sign_flip`, `misattributed`, `invented`, `wrong_direction`). On the full dataset (weeks 2010-12-06..2011-11-28, seed 7) the result is **precision 1.000, recall 1.000 on 120 cases**. Seeds 1–5 give the same result.

The planted errors are synthetic and the checker is exact matching by design, so this number shows the checker does what it claims on those six error kinds. It says nothing about how often the LLM writes a clean narrative on its first try; the backfill summary (`backfill_summary.csv`, column `attempts`) records that.

## Run it yourself

```bash
uv sync
export ANTHROPIC_API_KEY=...                            # never committed
tools/demo.sh                                           # downloads the data if needed, runs the 2 demo weeks locally, opens both reports
```

Re-render a saved week without calling the model ($0): rebuilds `report.md`/`report.html` from its `figures.json` + `narrative.json`, re-checks the narrative with the number checker, and with `--draft` also creates the Gmail draft:

```bash
uv run weekly-kpi-report render --from out/demo/2011-09-19            # local report only
uv run weekly-kpi-report render --from out/demo/2011-09-19 --draft    # + Gmail draft
```

`tools/demo.sh` runs week 2011-09-19 (a normal week, status `ok`) and week 2011-12-05 (flagged "Needs review"), writes `out/demo/<week>/report.html|md|figures.json` and never touches Gmail. Estimated about $0.03 per run.

Every command:

```bash
uv run weekly-kpi-report download                       # data/raw/online_retail_II.xlsx, SHA-256 checked
uv run weekly-kpi-report eval-checker --data data/raw/online_retail_II.xlsx --from 2010-12-06 --to 2011-11-28 --out out/eval
uv run weekly-kpi-report backfill --data data/raw/online_retail_II.xlsx --from 2010-12-06 --to 2011-12-05 --out out/backfill
uv run weekly-kpi-report run --data data/raw/online_retail_II.xlsx --as-of 2011-09-26 --no-gmail   # local report for week 2011-09-19
uv run weekly-kpi-report auth                           # one-time Gmail OAuth, scope gmail.compose only
uv run weekly-kpi-report run --data data/raw/online_retail_II.xlsx --as-of 2011-09-26              # + Gmail draft
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

## Results

Real runs on 2026-11-06 with `claude-sonnet-5-5`, local output only. The data is the public UCI Online Retail II set, a UK online giftware retailer from 2009-12 to 2011-12, so all dates are 2009–2011; nothing here is live shop data.

Latest demo render, 2026-11-08 (round 4): week 2011-09-19 re-rendered without the model from its saved 2026-11-06 narrative (it still passes the checker against the 52-figure set); week 2011-12-05 got one new narrative call ($0.016, first attempt, 0 violations).

| Week | Status | What the report says |
| --- | --- | --- |
| 2011-09-19 | `ok` | Hero revenue £328 713 with "+46.8% vs last week" and "+37.4% vs last year"; amber chips and 12-week spark-columns per key number; "Look at this": keep the top seller in stock |
| 2011-12-05 | `needs_review` | Banner: partial week (data stops Friday 2011-12-09) and £172 782 of products cancelled. Hero: revenue after cancellations £310 943 (booked £483 725). Cause card: `1 order: PAPER CRAFT , LITTLE BIRDIE ×80 995 · £168 470 → cancelled 12 min later`; without it revenue is £315 256, +1.9% vs last week. "Look at this": check cancellation C581484, re-run once the rest of the week is in. Headline: "the revenue jump is not good news" |

- **Why week 2011-12-05 matters:** its top "sale" is one order of 80 995 units cancelled 12 minutes later (invoices 581483 / C581484). Revenue is gross, so without the cause card the week reads as a +56.4% jump; the code finds the order, links it to its cancellation and shows the week without it (≈ flat). The narrative now explains the week through that order because the code passes it the same cause condition the card uses.
- **Number check on real narratives:** 8 real runs of the two demo weeks on 2026-11-06: 7 passed on the first attempt, 1 needed one retry, none was withheld. After the switch to the U+202F separator (2026-11-08) the model wrote plain spaces and the first call was withheld; since round 4 the model's text has plain or no-break spaces between digit groups normalised to U+202F before the check, and the next call passed first time. Estimated cost about $0.014 per week (the code's estimate at $2 / $10 per million input / output tokens).
- **Full backfill (53 weeks, 2010-12-06..2011-12-05, run 2026-11-06):** 50 `ok`, 2 `needs_review`, 1 `no_data`. The 52 weeks with sales got a narrative that passed the number check: 51 on the first attempt, 1 (2011-08-29) after one retry, none withheld. `needs_review`: 2011-01-17 (large cancellations: £78 841 against £209 331 revenue) and 2011-12-05 (partial week + large cancellations). `no_data`: 2010-12-27 (the week between Christmas and New Year, no sales lines). Logged cost $0.77 (the code's estimate at $2 / $10 per million input / output tokens).
- **Large-cancellation flag:** on the full dataset it fires on 2 of 104 weeks (2011-01-17 and 2011-12-05), both real giant orders cancelled the same week.
- **Checker eval:** precision 1.000, recall 1.000 on 120 planted cases (see Measured).

## Known limits

- The checker checks numbers and direction words only: not wording outside the closed list ("best week ever", "slightly", "surged"), wrong product or country names, claims without numbers, or spelled-out numbers ("five").
- Revenue is gross: cancellations are shown next to it (cancelled value, revenue after cancellations) and flagged at 25% of revenue or more, not netted out, and a cancellation is not matched to the week of its original order.
- Wholesale and retail customers are mixed, so the average order value blends both. No margin, stock or returns data exists in this dataset.
- Many product lines have no customer ID (2 517 of 13 181 in week 2011-09-19, 6 183 of 17 225 in week 2011-12-05); the report says so, and "Customers" counts only lines with one.
- "Sources" and "All figures" use `<details>`, which folds them away in a browser; email-client support varies. Both demo weeks were created as real Gmail drafts on 2026-11-08 (`render --draft`), not yet inspected in Gmail by a person.
- Failure handling seen for real: when the API account ran out of credit mid-run, every affected week was still written with figures only and flagged `needs_review` ("model call failed: BadRequestError").
- Mail clients turn the two licence URLs in the footer into links in their own blue, which is low-contrast on the dark page; the footer text must stay exact (attribution), so it isn't restyled.
- The model tends to write thousands with a plain space; the pipeline turns a plain or no-break space between a digit and exactly three digits into U+202F before checking. Side effect, failing safe: two separate numbers like "5 100 times" are joined into one and rejected by the checker. Only one call has been measured under this rule; the backfill pass rate under the new format is not re-measured.
- Next step (not built): let the model write only markers (`[F3]`) and have code insert the display, so no number is ever copied by the model.
- The schedule files are examples; nothing is installed, and a human presses send on every draft.

## Development

`make check` (ruff, mypy strict, security scans, unit tests) · `make test` · acceptance tests: `uv run pytest tests/acceptance`. The spec with all acceptance criteria is `specs/weekly-kpi-report.md`. All external services (Anthropic, Gmail, the download) are mocked in tests.

## Data

Data: Online Retail II (Chen, D., 2012), UCI Machine Learning Repository, https://doi.org/10.24432/C5CG6D — licensed CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).

The raw file is downloaded by a script and is not committed. Customer ids are numeric pseudonyms in the source and never appear in any output.
