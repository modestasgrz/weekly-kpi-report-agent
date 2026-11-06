"""AC-30 — Given a fake LLM whose first reply contains '£134 [F3]' and whose second is valid, when Run W, then each user message holds exactly one <week-data-R> block (R = 16 hex chars), the two R differ, both system prompts are equal, mention "week-data-" and contain neither R."""

import re
from pathlib import Path

import pytest
from kpi_helpers import GOOD, WRONG, FakeLLM, install, run_week, write_workbook


def test_ac_30_random_fence_tag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm, _ = install(monkeypatch, FakeLLM([WRONG, GOOD]))
    run_week(write_workbook(tmp_path / "f.xlsx"), tmp_path / "out")
    assert len(llm.calls) == 2
    codes = []
    for _, user in llm.calls:
        opened = re.findall(r"<week-data-([0-9a-f]{16})>", user)
        assert len(opened) == 1
        assert user.count(f"</week-data-{opened[0]}>") == 1
        codes.append(opened[0])
    assert codes[0] != codes[1]
    systems = [system for system, _ in llm.calls]
    assert systems[0] == systems[1]
    assert "week-data-" in systems[0]
    assert all(code not in systems[0] for code in codes)
