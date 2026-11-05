"""AC-14 — Given a fake LLM that always replies "not json", when Run W, then 3 calls, needs_review with reason "model output invalid", exit 2."""

from pathlib import Path

import pytest
from kpi_helpers import (
    FakeLLM,
    install,
    report,
    run_week,
    write_workbook,
)


def test_ac_14_invalid_model_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm, _ = install(monkeypatch, FakeLLM(["not json"]))
    out = tmp_path / "out"
    code = run_week(write_workbook(tmp_path / "f.xlsx"), out)
    r = report(out)
    assert len(llm.calls) == 3
    assert r["status"] == "needs_review"
    assert "model output invalid" in r["reasons"]
    assert code == 2
