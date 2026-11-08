"""AC-35 — A 1 000-unit order cancelled 12 minutes later: F44–F52, `cause`, `cancelled_products` and a 12-week `history` are computed in code; customer ids never reach the reports."""

from pathlib import Path

import pytest
from kpi_helpers import (
    BIRD,
    FakeLLM,
    d,
    figs,
    install,
    narrative,
    report,
    run_week,
    write_workbook,
)

ORDER = ("581009", "84879", BIRD, 1000, d("2011-12-02 09:15"), 1.69, 13000, "France")
CANCEL = ("C581010", "84879", BIRD, -1000, d("2011-12-02 09:27"), 1.69, 13000, "France")
NB = " "
CAUSE_GOOD = narrative(
    f"Revenue booked £1{NB}833 [F3], £137 [F44] after cancellations",
    [f"One order of £1{NB}690 [F45] was cancelled 12 [F48] minutes later."],
)


def test_ac_35_cause_figures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    llm, _ = install(monkeypatch, FakeLLM([CAUSE_GOOD]))
    out = tmp_path / "out"
    run_week(write_workbook(tmp_path / "f.xlsx", extra=[ORDER, CANCEL]), out)
    assert len(llm.calls) == 1
    f = figs(out)
    expected = {
        "F3": f"£1{NB}833",
        "F44": "£137",
        "F45": f"£1{NB}690",
        "F46": f"1{NB}000",
        "F47": "92.2%",
        "F48": "12",
        "F49": "£143",
        "F50": "+39.8%",
        "F51": f"£1{NB}690",
        "F52": "99.7%",
    }
    assert {k: f[k]["display"] for k in expected} == expected
    assert f["F45"]["label"] == BIRD
    r = report(out)
    assert r["cause"] == {
        "product": BIRD,
        "invoice": "581009",
        "cancel_invoice": "C581010",
        "rule": "top_line",
    }
    assert r["cancelled_products"] == ["F26"]
    assert set(r["history"]) == {"revenue", "orders", "aov", "customers"}
    assert all(len(v) == 12 for v in r["history"].values())
    assert r["history"]["revenue"][-1] == pytest.approx(f["F3"]["value"])
    assert r["violations"] == []
    for name in ["report.html", "report.md", "figures.json", "narrative.json"]:
        text = (out / "2011-11-28" / name).read_text()
        assert "13000" not in text and "12345" not in text, name
