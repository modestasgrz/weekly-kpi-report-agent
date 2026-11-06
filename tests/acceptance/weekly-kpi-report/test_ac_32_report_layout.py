"""AC-32 — report.html is email-safe (inline styles only, no external resources, no [Fn] left), key numbers show "<wow> vs last week", order headline < key numbers < narrative < All figures < attribution; no "Needs review" on an ok week; a partial week gets a "Needs review" banner with plain words before the headline."""

import re
from pathlib import Path

import pytest
from kpi_helpers import GOOD, NO_NUMBERS, FakeLLM, install, run_week, write_workbook

LINE = "Data: Online Retail II (Chen, D., 2012)"


def test_ac_32_report_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, FakeLLM([GOOD]))
    out = tmp_path / "out"
    run_week(write_workbook(tmp_path / "f.xlsx"), out)
    page = (out / "2011-11-28" / "report.html").read_text()
    md = (out / "2011-11-28" / "report.md").read_text()
    for banned in ["<style", "<script", "<link", "<img", "src=", "url(", "class="]:
        assert not re.search(re.escape(banned), page, re.IGNORECASE), banned
    assert "[F" not in page
    for change in ["+39.8%", "+50.0%", "-6.8%", "+100.0%"]:
        assert f"{change} vs last week" in page, change
    order = [
        page.index("Revenue reached £143"),
        page.index("vs last week"),
        page.index("led with £77"),
        page.index("All figures"),
        page.index(LINE),
    ]
    assert order == sorted(order)
    assert "Needs review" not in page
    assert "Needs review" not in md
    assert "+39.8% vs last week" in md

    install(monkeypatch, FakeLLM([NO_NUMBERS]))
    partial = tmp_path / "partial"
    run_week(write_workbook(tmp_path / "g.xlsx"), partial, "2011-12-12")
    page = (partial / "2011-12-05" / "report.html").read_text()
    md = (partial / "2011-12-05" / "report.md").read_text()
    for text in [page, md]:
        assert "Needs review" in text
        assert "Data stops on Monday 2011-12-05" in text
    assert page.index("Needs review") < page.index("Weekly sales summary")
