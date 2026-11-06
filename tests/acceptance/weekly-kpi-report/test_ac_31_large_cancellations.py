"""AC-31 — Given the fixture, when Run W, then F43 = "£5" (cancelled_value) and status ok; with an extra £51 cancellation line, F43 = "£56", needs_review with reason "large cancellations: £56 cancelled against £143 revenue", exit 2."""

from pathlib import Path

import pytest
from kpi_helpers import (
    CAKE,
    GOOD,
    FakeLLM,
    d,
    figs,
    install,
    report,
    run_week,
    write_workbook,
)

EXTRA = ("C581007", "22423", CAKE, -4, d("2011-12-03 10:00"), 12.75, 13000, "France")


def test_ac_31_large_cancellations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch, FakeLLM([GOOD]))
    base = tmp_path / "base"
    run_week(write_workbook(tmp_path / "f.xlsx"), base)
    f = figs(base)
    assert (f["F43"]["key"], f["F43"]["display"]) == ("cancelled_value", "£5")
    assert report(base)["status"] == "ok"

    install(monkeypatch, FakeLLM([GOOD]))
    out = tmp_path / "out"
    code = run_week(write_workbook(tmp_path / "g.xlsx", extra=[EXTRA]), out)
    r = report(out)
    assert figs(out)["F43"]["display"] == "£56"
    assert r["status"] == "needs_review"
    assert "large cancellations: £56 cancelled against £143 revenue" in r["reasons"]
    assert code == 2
