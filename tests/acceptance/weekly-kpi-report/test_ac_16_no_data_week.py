"""AC-16 — Given the fixture (no lines in 2011-11-14..2011-11-20), when run --as-of 2011-11-21, then no_data, 0 LLM and 0 draft calls, report.md contains "No sales data for week 2011-11-14", exit 3."""

from pathlib import Path

import pytest
from kpi_helpers import (
    install,
    report,
    run_week,
    write_workbook,
)


def test_ac_16_no_data_week(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    llm, gmail = install(monkeypatch)
    out = tmp_path / "out"
    code = run_week(write_workbook(tmp_path / "f.xlsx"), out, "2011-11-21")
    assert report(out, "2011-11-14")["status"] == "no_data"
    assert (len(llm.calls), len(gmail.calls)) == (0, 0)
    assert (
        "No sales data for week 2011-11-14"
        in (out / "2011-11-14" / "report.md").read_text()
    )
    assert code == 3
