"""AC-18 — Given KPI_COST_CAP_USD=0.01 and a fake LLM reporting 1,000,000 input tokens and replying "not json", when Run W, then exactly 1 call, reason "cost cap reached", exit 2."""

from pathlib import Path

import pytest
from kpi_helpers import (
    FakeLLM,
    install,
    report,
    run_week,
    write_workbook,
)


def test_ac_18_cost_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KPI_COST_CAP_USD", "0.01")
    llm, _ = install(monkeypatch, FakeLLM(["not json"], input_tokens=1_000_000))
    out = tmp_path / "out"
    code = run_week(write_workbook(tmp_path / "f.xlsx"), out)
    assert len(llm.calls) == 1
    assert "cost cap reached" in report(out)["reasons"]
    assert code == 2
