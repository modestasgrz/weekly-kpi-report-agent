"""AC-09 — Given the Run W figures, when check_narrative runs on "Units reached 3 [F6].", then it returns exactly one violation, kind wrong_reference, token "3"."""

from pathlib import Path

import pytest
from kpi_helpers import week_figures


def test_ac_09_checker_wrong_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from weekly_kpi_report_agent.checker import check_narrative

    figures = week_figures(tmp_path, monkeypatch)
    violations = check_narrative("Units reached 3 [F6].", figures)
    assert [(v.kind, v.token) for v in violations] == [("wrong_reference", "3")]
