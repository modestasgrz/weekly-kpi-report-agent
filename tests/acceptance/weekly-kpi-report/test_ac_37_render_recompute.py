"""AC-37 — `render --from DIR --data <xlsx>` recomputes an older run's figures (44 → 52) and round-4 fields from the data without any model call."""

import json
from pathlib import Path

import pytest
from kpi_helpers import GOOD, FakeLLM, cli, install, report, run_week, write_workbook


def test_ac_37_render_recompute(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    install(monkeypatch, FakeLLM([GOOD]))
    out = tmp_path / "out"
    data = write_workbook(tmp_path / "f.xlsx")
    run_week(data, out, "2011-12-05", "--no-gmail")
    week = out / "2011-11-28"
    original = json.loads((week / "figures.json").read_text())
    saved = json.loads((week / "figures.json").read_text())
    saved["figures"] = saved["figures"][:44]
    for key in ["history", "cause", "cancelled_products"]:
        saved.pop(key, None)
    (week / "figures.json").write_text(json.dumps(saved))

    llm, _ = install(monkeypatch, FakeLLM([RuntimeError("no model calls")]))
    assert cli("render", "--from", str(week)) == 1
    assert (
        f"error: {week} was written by an older version; re-run with --data <xlsx>"
        in capsys.readouterr().err
    )
    assert cli("render", "--from", str(week), "--data", str(data)) == 0
    assert llm.calls == []
    r = report(out)
    assert r["figures"] == original["figures"]
    for key in ["history", "cause", "cancelled_products"]:
        assert r[key] == original[key], key
    assert r["status"] == "ok"
