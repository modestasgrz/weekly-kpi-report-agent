"""AC-12 — Given a fake LLM whose first reply contains '£134 [F3]' and whose second reply is valid, when Run W, then status ok, attempts 2, and the second call's user message contains '£134'."""

from pathlib import Path

import pytest
from kpi_helpers import (
    GOOD,
    WRONG,
    FakeLLM,
    install,
    report,
    run_week,
    write_workbook,
)


def test_ac_12_retry_with_feedback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm, _ = install(monkeypatch, FakeLLM([WRONG, GOOD]))
    out = tmp_path / "out"
    run_week(write_workbook(tmp_path / "f.xlsx"), out)
    r = report(out)
    assert (r["status"], r["attempts"]) == ("ok", 2)
    assert len(llm.calls) == 2
    assert "£134" in llm.calls[1][1]
