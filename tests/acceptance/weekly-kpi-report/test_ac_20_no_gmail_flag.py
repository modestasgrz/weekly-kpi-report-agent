"""AC-20 — Given a valid fake LLM, when Run W with --no-gmail, then 0 draft calls, draft_id null, status ok, exit 0."""

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


def test_ac_20_no_gmail_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, gmail = install(monkeypatch, FakeLLM([GOOD]))
    out = tmp_path / "out"
    code = run_week(
        write_workbook(tmp_path / "f.xlsx"), out, "2011-12-05", "--no-gmail"
    )
    r = report(out)
    assert gmail.calls == []
    assert (r["draft_id"], r["status"], code) == (None, "ok", 0)
