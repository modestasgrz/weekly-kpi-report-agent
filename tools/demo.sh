#!/usr/bin/env bash
# Run the two demo weeks end to end (real Claude narrative, local output only, no Gmail) and open both reports.
# 2011-09-19 = a normal week (status ok), 2011-12-05 = flagged for review (partial week + a huge cancelled order).
# needs ANTHROPIC_API_KEY in the environment; cost about $0.03.
# usage: tools/demo.sh [out-dir]
set -euo pipefail
cd "$(dirname "$0")/.."
out="${1:-out/demo}"
data=data/raw/online_retail_II.xlsx
[ -f "$data" ] || uv run weekly-kpi-report download
for as_of in 2011-09-26 2011-12-12; do
  code=0
  uv run weekly-kpi-report run --data "$data" --as-of "$as_of" --out "$out" --no-gmail || code=$?
  case $code in 0) echo "week before $as_of: ok" ;; 2) echo "week before $as_of: NEEDS REVIEW (see the banner)" ;; *) exit "$code" ;; esac
done
for week in 2011-09-19 2011-12-05; do
  open "$out/$week/report.html" 2>/dev/null || xdg-open "$out/$week/report.html" || echo "report: $out/$week/report.html"
done
