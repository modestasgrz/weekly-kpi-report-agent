"""AC-06 — Given the fixture, when Run W, then 52 figures, every figure with display != "n/a" has a non-empty source, and the source of F3 contains "4 product lines" and "2011-11-28..2011-12-04"."""

from pathlib import Path

import pytest
from kpi_helpers import figs, install, run_week, write_workbook


def test_ac_06_figure_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch)
    run_week(write_workbook(tmp_path / "f.xlsx"), tmp_path / "out")
    f = figs(tmp_path / "out")
    assert len(f) == 52
    assert all(x["source"].strip() for x in f.values() if x["display"] != "n/a")
    assert "4 product lines" in f["F3"]["source"]
    assert "2011-11-28..2011-12-04" in f["F3"]["source"]
