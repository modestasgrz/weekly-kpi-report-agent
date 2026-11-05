"""AC-02 — Given the fixture, when Run W, then the WoW / 4-week / YoY change figures F11-F25 (except F13) have the displays listed in the spec."""

from pathlib import Path

import pytest
from kpi_helpers import figs, install, run_week, write_workbook


def test_ac_02_comparisons(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch)
    run_week(write_workbook(tmp_path / "f.xlsx"), tmp_path / "out")
    f = figs(tmp_path / "out")
    expected = {
        "F11": "+39.8%",
        "F12": "+459.1%",
        "F14": "+50.0%",
        "F15": "+500.0%",
        "F16": "+200.0%",
        "F17": "-6.8%",
        "F18": "-6.8%",
        "F19": "-37.9%",
        "F20": "+66.7%",
        "F21": "+566.7%",
        "F22": "+566.7%",
        "F23": "+100.0%",
        "F24": "+700.0%",
        "F25": "+100.0%",
    }
    assert {k: f[k]["display"] for k in expected} == expected
