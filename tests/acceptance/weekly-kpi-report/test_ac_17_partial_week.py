"""AC-17 — Given the fixture (last line 2011-12-05 09:00), when run --as-of 2011-12-12 with a valid fake LLM, then needs_review with reason "partial week: data ends 2011-12-05", exit 2."""

from pathlib import Path

import pytest
from kpi_helpers import (
    NO_NUMBERS,
    FakeLLM,
    install,
    report,
    run_week,
    write_workbook,
)


def test_ac_17_partial_week(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, FakeLLM([NO_NUMBERS]))
    out = tmp_path / "out"
    code = run_week(write_workbook(tmp_path / "f.xlsx"), out, "2011-12-12")
    r = report(out, "2011-12-05")
    assert r["status"] == "needs_review"
    assert "partial week: data ends 2011-12-05" in r["reasons"]
    assert code == 2
