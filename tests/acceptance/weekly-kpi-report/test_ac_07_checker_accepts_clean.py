"""AC-07 — Given the Run W figures, when check_narrative runs on a clean sentence (all numbers verbatim with correct markers, quoted product name containing a digit), then it returns an empty list."""

from pathlib import Path

import pytest
from kpi_helpers import week_figures


def test_ac_07_checker_accepts_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from weekly_kpi_report_agent.checker import check_narrative

    figures = week_figures(tmp_path, monkeypatch)
    text = 'Revenue reached £143 [F3] from 3 [F4] orders in the week of 2011-11-28 [F1]; "REGENCY CAKESTAND 3 TIER" led with £77 [F26].'
    assert check_narrative(text, figures) == []
