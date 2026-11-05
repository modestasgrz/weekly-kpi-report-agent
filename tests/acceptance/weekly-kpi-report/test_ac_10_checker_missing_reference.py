"""AC-10 — Given the Run W figures, when check_narrative runs on "Revenue was £143. REGENCY CAKESTAND 3 TIER sold well.", then it returns exactly two missing_reference violations with tokens "£143" and "3"."""

from pathlib import Path

import pytest
from kpi_helpers import week_figures


def test_ac_10_checker_missing_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from weekly_kpi_report_agent.checker import check_narrative

    figures = week_figures(tmp_path, monkeypatch)
    violations = check_narrative(
        "Revenue was £143. REGENCY CAKESTAND 3 TIER sold well.", figures
    )
    assert sorted((v.kind, v.token) for v in violations) == [
        ("missing_reference", "3"),
        ("missing_reference", "£143"),
    ]
