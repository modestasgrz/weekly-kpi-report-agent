"""AC-36 — Review week: hero = revenue after cancellations, cause card, code-written "Look at this", ✕ cancelled mark, 4×12 spark-columns, no citation superscripts; normal week hero = revenue; partial week chips say not comparable."""

from pathlib import Path

import pytest
from kpi_helpers import (
    GOOD,
    NO_NUMBERS,
    FakeLLM,
    install,
    report,
    run_week,
    write_workbook,
)
from test_ac_35_cause_figures import CANCEL, CAUSE_GOOD, ORDER

NB = " "


def test_ac_36_hero_cause_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch, FakeLLM([CAUSE_GOOD]))
    out = tmp_path / "out"
    run_week(write_workbook(tmp_path / "f.xlsx", extra=[ORDER, CANCEL]), out)
    page = (out / "2011-11-28" / "report.html").read_text()
    body = page[page.index("<body") :]
    order = [
        "Revenue after cancellations",
        "£137",
        f"Booked £1{NB}833",
        f"1 order: ASSORTED COLOUR BIRD ORNAMENT ×1{NB}000 · £1{NB}690 → cancelled 12 min later",
        "Look at this",
        "Check cancellation C581010: was &quot;ASSORTED COLOUR BIRD ORNAMENT&quot; a lost sale or a mistake?",
    ]
    at = body.index(order[0])
    for text in order[1:]:
        at = body.index(text, at)
    assert "✕ cancelled" in body
    assert body.count('valign="bottom"') == 48
    assert "<sup" not in page
    assert "in stock" not in body

    install(monkeypatch, FakeLLM([GOOD]))
    normal = tmp_path / "normal"
    run_week(write_workbook(tmp_path / "g.xlsx"), normal)
    page = (normal / "2011-11-28" / "report.html").read_text()
    body = page[page.index("<body") :]
    assert ">Revenue after cancellations<" not in body
    assert "1 order:" not in body
    hero = body.index(">Revenue<")
    assert hero < body.index("£143", hero)
    assert report(normal)["cause"] is None

    install(monkeypatch, FakeLLM([NO_NUMBERS]))
    partial = tmp_path / "partial"
    run_week(write_workbook(tmp_path / "h.xlsx"), partial, "2011-12-12")
    page = (partial / "2011-12-05" / "report.html").read_text()
    assert "partial week, not comparable" in page
    assert "Re-run this report once the data after 2011-12-05 is in." in page
    assert "Find out why" not in page
