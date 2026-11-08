import json
import re
from pathlib import Path

import numpy as np
import pytest

from weekly_kpi_report_agent.checker import TOKEN
from weekly_kpi_report_agent.cli import main
from weekly_kpi_report_agent.evalset import plant
from weekly_kpi_report_agent.kpis import count, money
from weekly_kpi_report_agent.models import Figure, WeekReport
from weekly_kpi_report_agent.report import plain

NB = " "


def fig(fid: str, key: str, display: str, value: float) -> Figure:
    return Figure(id=fid, key=key, label=key, value=value, display=display, source="s")


def test_displays_group_thousands_with_narrow_no_break_space() -> None:
    assert money(1234567.4) == f"£1{NB}234{NB}567"
    assert count(13181) == f"13{NB}181"
    assert money(999.4) == "£999"


def test_plain_large_cancellations_keeps_grouped_amount() -> None:
    reason = f"large cancellations: £172{NB}782 cancelled against £483{NB}725 revenue"
    assert plain(reason).startswith(f"£172{NB}782 of products were cancelled")


@pytest.mark.parametrize(
    "kind", ["digit_swap", "rounding", "misattributed", "sign_flip"]
)
def test_plant_replaces_the_whole_grouped_number(kind: str) -> None:
    figures = {
        "F3": fig("F3", "revenue", f"£328{NB}713", 328713.0),
        "F4": fig("F4", "orders", "463", 463.0),
        "F11": fig("F11", "revenue_wow", "+46.8%", 46.8),
    }
    text = f"Revenue reached £328{NB}713 [F3] from 463 [F4], up +46.8% [F11]."
    rng = np.random.default_rng(1)
    for _ in range(20):
        planted = plant(kind, text, figures, rng)
        assert planted is not None and planted != text
        tokens = [m.group(0) for m in TOKEN.finditer(planted)]
        assert all("£" not in t[1:] for t in tokens)
        assert not re.search(r"£\d+ £", planted)


def saved_week(tmp_path: Path) -> Path:
    week = WeekReport(
        week_start="2011-11-28",
        status="ok",
        reasons=[],
        attempts=1,
        figures=[fig("F52", "top_cancel_share", "n/a", 0.0)],
        anomalies=[],
        violations=[],
        draft_id=None,
    )
    folder = tmp_path / "2011-11-28"
    folder.mkdir()
    (folder / "figures.json").write_text(week.model_dump_json())
    return folder


def test_render_without_figures_json_is_an_input_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["render", "--from", str(tmp_path)]) == 1
    assert f"error: no run in {tmp_path}" in capsys.readouterr().err


def test_render_with_invalid_narrative_json_rewrites_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = saved_week(tmp_path)
    (folder / "narrative.json").write_text(json.dumps({"headline": ""}))
    before = (folder / "figures.json").read_text()
    assert main(["render", "--from", str(folder)]) == 1
    assert "invalid narrative.json" in capsys.readouterr().err
    assert (folder / "figures.json").read_text() == before
    assert not (folder / "report.md").exists()
