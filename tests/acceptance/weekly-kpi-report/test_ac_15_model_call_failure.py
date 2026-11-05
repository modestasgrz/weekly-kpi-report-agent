"""AC-15 — Given a fake LLM that raises RuntimeError("provider 500"), when Run W, then needs_review with reason "model call failed: RuntimeError", report.md and figures.json exist, no output file contains "provider 500", exit 2."""

from pathlib import Path

import pytest
from kpi_helpers import (
    FakeLLM,
    install,
    report,
    run_week,
    write_workbook,
)


def test_ac_15_model_call_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch, FakeLLM([RuntimeError("provider 500")]))
    out = tmp_path / "out"
    code = run_week(write_workbook(tmp_path / "f.xlsx"), out)
    r = report(out)
    assert r["status"] == "needs_review"
    assert "model call failed: RuntimeError" in r["reasons"]
    assert (out / "2011-11-28" / "report.md").exists()
    assert all(
        "provider 500" not in p.read_text() for p in out.rglob("*") if p.is_file()
    )
    assert code == 2
