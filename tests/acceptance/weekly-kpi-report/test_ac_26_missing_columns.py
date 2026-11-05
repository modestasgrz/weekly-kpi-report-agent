"""AC-26 — Given a workbook without the Price column, when run, then exit 1, stderr contains "missing columns: Price", and no output directory is created."""

from pathlib import Path

import pytest
from kpi_helpers import install, run_week, write_workbook


def test_ac_26_missing_columns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    install(monkeypatch)
    out = tmp_path / "out"
    code = run_week(write_workbook(tmp_path / "f.xlsx", drop=["Price"]), out)
    assert code == 1
    assert "missing columns: Price" in capsys.readouterr().err
    assert not out.exists()
