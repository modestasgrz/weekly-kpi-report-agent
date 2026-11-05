import argparse
import csv
import os
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path

from loguru import logger

from weekly_kpi_report_agent import gmail
from weekly_kpi_report_agent.data import clean, missing_columns, read
from weekly_kpi_report_agent.download import ChecksumError, download
from weekly_kpi_report_agent.evalset import evaluate
from weekly_kpi_report_agent.pipeline import Budget, run_week

EXIT_CODES = {"ok": 0, "needs_review": 2, "no_data": 3}


def weeks(first: date, last: date) -> list[date]:
    start = first - timedelta(days=first.weekday())
    return (
        [start + timedelta(days=7 * i) for i in range((last - start).days // 7 + 1)]
        if last >= first
        else []
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="weekly-kpi-report",
        description="Weekly sales KPI report: figures computed in code, narrative by Claude, every number checked.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("download", help="download the UCI Online Retail II dataset")
    p.add_argument("--dest", type=Path, default=Path("data/raw"))
    p = sub.add_parser("run", help="report the latest complete week before --as-of")
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    p.add_argument("--out", type=Path, default=Path("out"))
    p.add_argument("--no-gmail", action="store_true")
    for name in ["backfill", "eval-checker"]:
        p = sub.add_parser(
            name,
            help="local reports for every week in the range"
            if name == "backfill"
            else "precision/recall of the number checker on planted errors",
        )
        p.add_argument("--data", type=Path, required=True)
        p.add_argument("--from", dest="first", type=date.fromisoformat, required=True)
        p.add_argument("--to", dest="last", type=date.fromisoformat, required=True)
        p.add_argument("--out", type=Path, default=Path("out"))
        if name == "eval-checker":
            p.add_argument("--seed", type=int, default=7)
    sub.add_parser(
        "auth", help="authorize Gmail drafts (gmail.compose scope) for the demo account"
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return 0 if e.code == 0 else 1

    try:
        if args.command == "auth":
            print(f"token written to {gmail.authorize()}")
            return 0
        if args.command == "download":
            print(f"dataset at {download(args.dest)}")
            return 0
        budget = Budget(cap_usd=float(os.environ.get("KPI_COST_CAP_USD", "5.0")))
        sheets = read(args.data)
        missing = missing_columns(sheets)
        if missing:
            print(f"error: missing columns: {', '.join(missing)}", file=sys.stderr)
            return 1
        df = clean(sheets)
    except ChecksumError:
        print(
            "error: checksum mismatch: the download is not the expected Online Retail II zip",
            file=sys.stderr,
        )
        return 1
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as e:
        print(f"error: could not read input ({type(e).__name__})", file=sys.stderr)
        return 1

    file_name = args.data.name
    if args.command == "run":
        week = run_week(
            df,
            args.as_of - timedelta(days=args.as_of.weekday() + 7),
            file_name,
            args.out,
            not args.no_gmail,
            budget,
        )
        logger.info("run done: 1 week, cost ${:.4f}", budget.spent_usd)
        return EXIT_CODES[week.status]
    if args.command == "backfill":
        args.out.mkdir(parents=True, exist_ok=True)
        with (args.out / "backfill_summary.csv").open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                ["week_start", "status", "attempts", "violations", "reasons"]
            )
            for start in weeks(args.first, args.last):
                week = run_week(df, start, file_name, args.out, False, budget)
                writer.writerow(
                    [
                        week.week_start,
                        week.status,
                        week.attempts,
                        len(week.violations),
                        "; ".join(week.reasons),
                    ]
                )
        logger.info("backfill done: cost ${:.4f}", budget.spent_usd)
        return 0
    try:
        result = evaluate(df, weeks(args.first, args.last), file_name, args.seed)
    except ValueError:
        print(
            "error: no week with sales data in the range, or too few to plant every error type",
            file=sys.stderr,
        )
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "checker_eval.json").write_text(result.model_dump_json(indent=2))
    logger.info("checker eval: precision {} recall {}", result.precision, result.recall)
    return 0
