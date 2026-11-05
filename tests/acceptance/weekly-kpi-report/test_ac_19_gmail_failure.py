"""AC-19 — Given a valid fake LLM and gmail.create_draft raising RuntimeError, when Run W, then report.md exists, draft_id null, needs_review with reason "gmail draft failed: RuntimeError", exit 2."""

from pathlib import Path

import pytest
from kpi_helpers import (
    GOOD,
    FakeGmail,
    FakeLLM,
    install,
    report,
    run_week,
    write_workbook,
)


def test_ac_19_gmail_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, FakeLLM([GOOD]), FakeGmail(RuntimeError("smtp secret")))
    out = tmp_path / "out"
    code = run_week(write_workbook(tmp_path / "f.xlsx"), out)
    r = report(out)
    assert (out / "2011-11-28" / "report.md").exists()
    assert r["draft_id"] is None
    assert r["status"] == "needs_review"
    assert "gmail draft failed: RuntimeError" in r["reasons"]
    assert code == 2
