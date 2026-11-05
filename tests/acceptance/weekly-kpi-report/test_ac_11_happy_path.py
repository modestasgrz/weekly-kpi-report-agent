"""AC-11 — Given a fake LLM returning a valid narrative whose numbers pass the checker, when Run W, then status ok, attempts 1, report.md has the headline and a footnote for every [Fn] used, one draft with subject "Weekly sales KPIs — week of 2011-11-28", exit 0."""

import re
from pathlib import Path

import pytest
from kpi_helpers import (
    GOOD,
    FakeLLM,
    install,
    report,
    run_week,
    write_workbook,
)


def test_ac_11_happy_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, gmail = install(monkeypatch, FakeLLM([GOOD]))
    out = tmp_path / "out"
    code = run_week(write_workbook(tmp_path / "f.xlsx"), out)
    r = report(out)
    assert (r["status"], r["attempts"], code) == ("ok", 1, 0)
    md = (out / "2011-11-28" / "report.md").read_text()
    assert "Revenue reached £143 [F3] in the week of 2011-11-28 [F1]" in md
    for marker in ["F1", "F3", "F4", "F11", "F26"]:
        assert re.search(rf"^\s*(?:[-*]\s*)?\[{marker}\]", md, re.MULTILINE), marker
    assert [c["subject"] for c in gmail.calls] == [
        "Weekly sales KPIs — week of 2011-11-28"
    ]
    assert r["draft_id"] == "draft-1"
