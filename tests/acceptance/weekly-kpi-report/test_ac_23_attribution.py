"""AC-23 — Given Run W, then report.md, report.html and README.md each contain the exact attribution line of DEC-12."""

from pathlib import Path

import pytest
from kpi_helpers import install, run_week, write_workbook

LINE = "Data: Online Retail II (Chen, D., 2012), UCI Machine Learning Repository, https://doi.org/10.24432/C5CG6D — licensed CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)."
README = Path(__file__).resolve().parents[3] / "README.md"


def test_ac_23_attribution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch)
    out = tmp_path / "out"
    run_week(write_workbook(tmp_path / "f.xlsx"), out)
    assert LINE in (out / "2011-11-28" / "report.md").read_text()
    assert LINE in (out / "2011-11-28" / "report.html").read_text()
    assert LINE in README.read_text()
