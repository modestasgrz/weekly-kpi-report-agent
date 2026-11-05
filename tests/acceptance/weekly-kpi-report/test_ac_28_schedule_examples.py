"""AC-28 — The launchd plist has StartCalendarInterval {"Weekday": 1, "Hour": 7, "Minute": 0} and "run" in ProgramArguments; deploy/crontab.example has a line starting "0 7 * * 1 "."""

import plistlib
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[3] / "deploy"


def test_ac_28_schedule_examples() -> None:
    plist = plistlib.loads(
        (DEPLOY / "com.portfolio.weekly-kpi-report.plist").read_bytes()
    )
    assert plist["StartCalendarInterval"] == {"Weekday": 1, "Hour": 7, "Minute": 0}
    assert "run" in plist["ProgramArguments"]
    lines = (DEPLOY / "crontab.example").read_text().splitlines()
    assert any(line.startswith("0 7 * * 1 ") for line in lines)
