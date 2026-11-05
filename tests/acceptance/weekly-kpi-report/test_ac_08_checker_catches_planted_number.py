"""AC-08 — Given the Run W figures, when check_narrative runs on "Revenue reached £134 [F3]." (planted wrong number), then it returns exactly one violation, kind unknown_number, token "£134"."""

from pathlib import Path

import pytest
from kpi_helpers import week_figures


def test_ac_08_checker_catches_planted_number(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from weekly_kpi_report_agent.checker import check_narrative

    figures = week_figures(tmp_path, monkeypatch)
    violations = check_narrative("Revenue reached £134 [F3].", figures)
    assert [(v.kind, v.token) for v in violations] == [("unknown_number", "£134")]
