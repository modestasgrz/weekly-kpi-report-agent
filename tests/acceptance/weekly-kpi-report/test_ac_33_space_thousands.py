"""AC-33 — Displays use a narrow no-break space (U+202F) as thousands separator; the checker accepts exactly that display and rejects a comma-grouped, wrong, plain-space-split or marker-split number."""

from pathlib import Path

import pytest
from kpi_helpers import CAKE, d, figs, install, run_week, write_workbook

EXTRA = ("581008", "22423", CAKE, 100, d("2011-12-01 10:00"), 12.75, 13000, "France")
NB = " "


def test_ac_33_space_thousands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from weekly_kpi_report_agent.checker import check_narrative
    from weekly_kpi_report_agent.models import Figure

    install(monkeypatch)
    out = tmp_path / "out"
    run_week(write_workbook(tmp_path / "f.xlsx", extra=[EXTRA]), out)
    raw = figs(out)
    assert raw["F3"]["display"] == f"£1{NB}418"
    figures = [Figure.model_validate(f) for f in raw.values()]

    assert check_narrative(f"Revenue reached £1{NB}418 [F3].", figures) == []
    comma = check_narrative("Revenue reached £1,418 [F3].", figures)
    assert [(v.kind, v.token) for v in comma] == [("unknown_number", "£1,418")]
    wrong = check_narrative(f"Revenue reached £1{NB}419 [F3].", figures)
    assert [(v.kind, v.token) for v in wrong] == [("unknown_number", f"£1{NB}419")]
    assert check_narrative("Revenue reached £1 418 [F3].", figures)
    assert check_narrative(f"Revenue reached £1 [F3]{NB}418.", figures)
