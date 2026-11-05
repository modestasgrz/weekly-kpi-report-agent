"""AC-13 — Given a fake LLM that always replies with "£134 [F3]", when Run W, then 3 calls, needs_review with reason "narrative failed number check after 3 attempts", report.md has "Narrative withheld" and the rejected sentence, subject prefixed "[NEEDS REVIEW] ", exit 2."""

from pathlib import Path

import pytest
from kpi_helpers import (
    WRONG,
    FakeLLM,
    install,
    report,
    run_week,
    write_workbook,
)


def test_ac_13_needs_review_after_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm, gmail = install(monkeypatch, FakeLLM([WRONG]))
    out = tmp_path / "out"
    code = run_week(write_workbook(tmp_path / "f.xlsx"), out)
    r = report(out)
    assert len(llm.calls) == 3
    assert r["status"] == "needs_review"
    assert "narrative failed number check after 3 attempts" in r["reasons"]
    md = (out / "2011-11-28" / "report.md").read_text()
    assert "Narrative withheld" in md
    assert "Revenue reached £134 [F3] this week." in md
    assert [c["subject"] for c in gmail.calls] == [
        "[NEEDS REVIEW] Weekly sales KPIs — week of 2011-11-28"
    ]
    assert code == 2
