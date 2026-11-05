"""AC-25 — Given the fixture, when eval-checker --from 2011-11-21 --to 2011-11-28 --seed 7, then checker_eval.json has 120 cases (60 clean, 60 planted), consistent confusion counts, precision/recall from them (3 decimals), six planted types with 10 each, and 0 LLM calls."""

import json
from pathlib import Path

import pytest
from kpi_helpers import cli, install, write_workbook

TYPES = [
    "digit_swap",
    "rounding",
    "sign_flip",
    "misattributed",
    "invented",
    "wrong_direction",
]


def test_ac_25_checker_eval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    llm, _ = install(monkeypatch)
    out = tmp_path / "out"
    data = str(write_workbook(tmp_path / "f.xlsx"))
    code = cli(
        "eval-checker",
        "--data",
        data,
        "--from",
        "2011-11-21",
        "--to",
        "2011-11-28",
        "--out",
        str(out),
        "--seed",
        "7",
    )
    r = json.loads((out / "checker_eval.json").read_text())
    assert (r["cases"], r["clean"], r["planted"]) == (120, 60, 60)
    tp, fp, tn, fn = (
        r["true_positive"],
        r["false_positive"],
        r["true_negative"],
        r["false_negative"],
    )
    assert tp + fn == 60
    assert fp + tn == 60
    assert tp + fp > 0
    assert r["precision"] == round(tp / (tp + fp), 3)
    assert r["recall"] == round(tp / (tp + fn), 3)
    assert sorted(r["by_type"]) == sorted(TYPES)
    for value in r["by_type"].values():
        assert (value if isinstance(value, int) else value["planted"]) == 10
    assert llm.calls == []
    assert code == 0
