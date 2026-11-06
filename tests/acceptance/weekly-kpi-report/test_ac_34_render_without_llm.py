"""AC-34 — run saves narrative.json; `render --from <week dir>` rebuilds the reports (and with --draft the Gmail draft) without calling the model, re-checking the saved narrative; a narrative that fails the check is withheld (needs_review, exit 2), and fixing it renders ok again."""

import json
from pathlib import Path

import pytest
from kpi_helpers import GOOD, FakeLLM, cli, install, report, run_week, write_workbook


def test_ac_34_render_without_llm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch, FakeLLM([GOOD]))
    out = tmp_path / "out"
    run_week(write_workbook(tmp_path / "f.xlsx"), out, "2011-12-05", "--no-gmail")
    week = out / "2011-11-28"
    assert json.loads((week / "narrative.json").read_text()) == json.loads(GOOD)
    (week / "report.md").unlink()
    (week / "report.html").unlink()

    llm, gmail = install(monkeypatch, FakeLLM([RuntimeError("no model calls")]))
    assert cli("render", "--from", str(week)) == 0
    assert llm.calls == []
    assert gmail.calls == []
    assert (week / "report.html").exists()
    md = (week / "report.md").read_text()
    assert "Revenue reached £143 [F3] in the week of 2011-11-28 [F1]" in md

    assert cli("render", "--from", str(week), "--draft") == 0
    assert [c["subject"] for c in gmail.calls] == [
        "Weekly sales KPIs — week of 2011-11-28"
    ]
    assert report(out)["draft_id"] == "draft-1"
    assert llm.calls == []

    saved = json.loads((week / "narrative.json").read_text())
    saved["headline"] = "Revenue reached £134 [F3]"
    (week / "narrative.json").write_text(json.dumps(saved))
    assert cli("render", "--from", str(week)) == 2
    r = report(out)
    assert r["status"] == "needs_review"
    assert "narrative failed number check on re-render" in r["reasons"]
    assert "Narrative withheld" in (week / "report.md").read_text()

    (week / "narrative.json").write_text(json.dumps(json.loads(GOOD)))
    assert cli("render", "--from", str(week)) == 0
    assert report(out)["status"] == "ok"
    assert llm.calls == []
