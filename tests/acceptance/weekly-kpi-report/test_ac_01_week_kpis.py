"""AC-01 — Given the fixture, when Run W, then F1 = "2011-11-28", F2 = "2011-12-04", F3 = "£143", F4 = "3", F5 = "£47.52", F6 = "40", F7 = "2", F8 = "1", F9 = "1", F10 = "25.0%"."""

from pathlib import Path

import pytest
from kpi_helpers import figs, install, run_week, write_workbook


def test_ac_01_week_kpis(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch)
    run_week(write_workbook(tmp_path / "f.xlsx"), tmp_path / "out")
    f = figs(tmp_path / "out")
    expected = {
        "F1": "2011-11-28",
        "F2": "2011-12-04",
        "F3": "£143",
        "F4": "3",
        "F5": "£47.52",
        "F6": "40",
        "F7": "2",
        "F8": "1",
        "F9": "1",
        "F10": "25.0%",
    }
    assert {k: f[k]["display"] for k in expected} == expected
