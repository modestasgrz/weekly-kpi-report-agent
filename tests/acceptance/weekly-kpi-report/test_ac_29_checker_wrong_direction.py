"""AC-29 — Given the Run W figures, when check_narrative runs on "Revenue fell +39.8% [F11] week on week.", then one wrong_direction violation with token "+39.8%"; on "Revenue rose +39.8% [F11], while average order value fell -6.8% [F17]." and on "Revenue moved +39.8% [F11]." it returns an empty list."""

from pathlib import Path

import pytest
from kpi_helpers import week_figures


def test_ac_29_checker_wrong_direction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from weekly_kpi_report_agent.checker import check_narrative

    figures = week_figures(tmp_path, monkeypatch)
    violations = check_narrative("Revenue fell +39.8% [F11] week on week.", figures)
    assert [(v.kind, v.token) for v in violations] == [("wrong_direction", "+39.8%")]
    assert (
        check_narrative(
            "Revenue rose +39.8% [F11], while average order value fell -6.8% [F17].",
            figures,
        )
        == []
    )
    assert check_narrative("Revenue moved +39.8% [F11].", figures) == []
