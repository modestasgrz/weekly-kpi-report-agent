"""AC-04 — Given the fixture, when Run W, then F37 = "1", F38 = "1", F39 = "1", F40 = "1", F41 = "1", F42 = "4"."""

from pathlib import Path

import pytest
from kpi_helpers import figs, install, run_week, write_workbook


def test_ac_04_exclusion_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch)
    run_week(write_workbook(tmp_path / "f.xlsx"), tmp_path / "out")
    f = figs(tmp_path / "out")
    expected = {"F37": "1", "F38": "1", "F39": "1", "F40": "1", "F41": "1", "F42": "4"}
    assert {k: f[k]["display"] for k in expected} == expected
