"""AC-05 — Given the fixture, when Run W, then F26 = "£77" (REGENCY CAKESTAND 3 TIER), F27 = "£41" (ASSORTED COLOUR BIRD ORNAMENT), F28 = "£26" (WHITE HANGING HEART T-LIGHT HOLDER), F31 = "£92" (United Kingdom), F32 = "£51" (France), and F29, F30, F33, F34, F35 are n/a with value null."""

from pathlib import Path

import pytest
from kpi_helpers import figs, install, run_week, write_workbook


def test_ac_05_top_lists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch)
    run_week(write_workbook(tmp_path / "f.xlsx"), tmp_path / "out")
    f = figs(tmp_path / "out")
    expected = {
        "F26": ("£77", "REGENCY CAKESTAND 3 TIER"),
        "F27": ("£41", "ASSORTED COLOUR BIRD ORNAMENT"),
        "F28": ("£26", "WHITE HANGING HEART T-LIGHT HOLDER"),
        "F31": ("£92", "United Kingdom"),
        "F32": ("£51", "France"),
    }
    assert {k: (f[k]["display"], f[k]["label"]) for k in expected} == expected
    for k in ["F29", "F30", "F33", "F34", "F35"]:
        assert (f[k]["display"], f[k]["value"]) == ("n/a", None)
