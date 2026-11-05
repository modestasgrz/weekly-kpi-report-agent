"""AC-24 — Given the fixture and a valid fake LLM, when backfill --from 2011-11-14 --to 2011-12-05, then backfill_summary.csv has 4 rows (no_data, ok, ok, needs_review), 0 draft calls, exit 0."""

import csv
from pathlib import Path

import pytest
from kpi_helpers import NO_NUMBERS, FakeLLM, cli, install, write_workbook


def test_ac_24_backfill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, gmail = install(monkeypatch, FakeLLM([NO_NUMBERS]))
    out = tmp_path / "out"
    data = str(write_workbook(tmp_path / "f.xlsx"))
    code = cli(
        "backfill",
        "--data",
        data,
        "--from",
        "2011-11-14",
        "--to",
        "2011-12-05",
        "--out",
        str(out),
    )
    with (out / "backfill_summary.csv").open() as fh:
        rows = list(csv.DictReader(fh))
    assert [(r["week_start"], r["status"]) for r in rows] == [
        ("2011-11-14", "no_data"),
        ("2011-11-21", "ok"),
        ("2011-11-28", "ok"),
        ("2011-12-05", "needs_review"),
    ]
    assert list(rows[0]) == [
        "week_start",
        "status",
        "attempts",
        "violations",
        "reasons",
    ]
    assert gmail.calls == []
    assert code == 0
