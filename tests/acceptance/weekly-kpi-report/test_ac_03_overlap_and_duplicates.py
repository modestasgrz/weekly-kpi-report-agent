"""AC-03 — Given the fixture, whose 2010-12-01 line is present in both sheets and whose line 3 is present twice, when Run W, then F13 = "+86.4%" (the overlap line counted once) and F36 = "1"."""

from pathlib import Path

import pytest
from kpi_helpers import figs, install, run_week, write_workbook


def test_ac_03_overlap_and_duplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch)
    run_week(write_workbook(tmp_path / "f.xlsx"), tmp_path / "out")
    f = figs(tmp_path / "out")
    assert f["F13"]["display"] == "+86.4%"
    assert f["F36"]["display"] == "1"
