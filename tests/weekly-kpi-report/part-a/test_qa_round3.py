import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest
from edge_support import (
    ROWS_B,
    FakeGmail,
    FakeLLM,
    cleaned,
    install,
    narrative,
    write_book,
)

from weekly_kpi_report_agent.checker import check_narrative
from weekly_kpi_report_agent.cli import main
from weekly_kpi_report_agent.kpis import compute_week
from weekly_kpi_report_agent.llm import LLMReply
from weekly_kpi_report_agent.models import Figure
from weekly_kpi_report_agent.pipeline import Budget, run_week

NB = " "
START = date(2011, 11, 28)
WEEK = "2011-11-28"
BIG: list[tuple[Any, ...]] = [
    (
        f"9{i:04d}",
        "10001",
        "AAA",
        1,
        datetime(2011, 11, 29, 10),
        1.0,
        float(i + 1),
        "United Kingdom",
    )
    for i in range(1199)
] + [
    (
        "80000",
        "10002",
        "BBB",
        100000,
        datetime(2011, 11, 30, 10),
        12.5,
        5000.0,
        "France",
    ),
    ("C90001", "10001", "AAA", -1000, datetime(2011, 12, 4, 10), 2.0, 1.0, "France"),
]
GOOD = narrative(
    f"Revenue reached £1{NB}251{NB}199 [F3]", f"There were 1{NB}200 [F4] orders."
)
BAD = narrative(f"Revenue reached £1{NB}251{NB}198 [F3]", "Orders were steady.")


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture(scope="module")
def figures() -> dict[str, Figure]:
    figs, _ = compute_week(cleaned(ROWS_B, BIG), START, "f.xlsx")
    return {f.key: f for f in figs}


@pytest.fixture(scope="module")
def figure_list() -> list[Figure]:
    figs, _ = compute_week(cleaned(ROWS_B, BIG), START, "f.xlsx")
    return figs


def kinds(text: str, figs: list[Figure]) -> list[tuple[str, str]]:
    return [(v.kind, v.token) for v in check_narrative(text, figs)]


def test_fixture_displays_are_the_expected_grouped_strings(
    figures: dict[str, Figure],
) -> None:
    assert figures["revenue"].display == f"£1{NB}251{NB}199"
    assert figures["orders"].display == f"1{NB}200"
    assert figures["aov"].display == f"£1{NB}042.67"
    assert figures["units"].display == f"101{NB}199"
    assert figures["customers"].display == f"1{NB}200"
    assert figures["cancelled_value"].display == f"£2{NB}000"
    assert figures["net_revenue"].display == f"£1{NB}249{NB}199"
    assert figures["product_lines"].display == f"1{NB}200"


def test_sources_group_counts_and_use_no_comma_or_plain_space(
    figures: dict[str, Figure],
) -> None:
    assert (
        f"over 1{NB}200 product lines, 2011-11-28..2011-12-04, f.xlsx"
        in figures["revenue"].source
    )
    assert f"over 1{NB}200 product lines" in figures["aov"].source
    assert "over 1 product cancellation lines" in figures["cancelled_value"].source
    assert "BBB over 1 product lines" in figures["product_1_revenue"].source
    assert f"AAA over 1{NB}199 product lines" in figures["product_2_revenue"].source
    for f in figures.values():
        for text in (f.display, f.source):
            assert not re.search(r"\d,\d{3}", text), (f.id, text)
            assert not re.search(r"(?<![\d.])\d{1,3} \d{3}(?!\d)", text), (f.id, text)


def test_money_figures_all_use_nb_space(figures: dict[str, Figure]) -> None:
    for key in [
        "revenue",
        "aov",
        "cancelled_value",
        "net_revenue",
        "product_1_revenue",
    ]:
        assert NB in figures[key].display
        assert "," not in figures[key].display


def test_change_figures_are_never_grouped(figures: dict[str, Figure]) -> None:
    changes = [f for f in figures.values() if re.search(r"_(wow|vs4w|yoy)$", f.key)]
    assert len(changes) == 15
    assert figures["revenue_wow"].display == "+2502298.0%"
    for f in changes:
        assert NB not in f.display and "," not in f.display and " " not in f.display
        assert f.display == "n/a" or re.fullmatch(r"[+-]\d+\.\d%", f.display)


def test_checker_accepts_nb_grouped_money_count_aov_and_millions(
    figure_list: list[Figure],
) -> None:
    text = (
        f"Revenue reached £1{NB}251{NB}199 [F3] from 1{NB}200 [F4] orders at £1{NB}042.67 [F5], "
        f"with 101{NB}199 [F6] units and £1{NB}249{NB}199 [F44] after £2{NB}000 [F43] cancelled."
    )
    assert kinds(text, figure_list) == []


def test_checker_accepts_ungrouped_change_and_rejects_grouped_change(
    figure_list: list[Figure],
) -> None:
    assert kinds("Revenue rose +2502298.0% [F11].", figure_list) == []
    assert kinds(f"Revenue rose +2{NB}502{NB}298.0% [F11].", figure_list) == [
        ("unknown_number", f"+2{NB}502{NB}298.0%")
    ]


def test_checker_rejects_comma_grouped_as_one_unknown_token(
    figure_list: list[Figure],
) -> None:
    assert kinds("Revenue reached £1,251,199 [F3].", figure_list) == [
        ("unknown_number", "£1,251,199")
    ]
    assert kinds("Revenue reached £1,251,199.", figure_list) == [
        ("missing_reference", "£1,251,199")
    ]


def test_checker_rejects_a_changed_grouped_number_as_a_whole(
    figure_list: list[Figure],
) -> None:
    assert kinds(f"Revenue reached £1{NB}251{NB}198 [F3].", figure_list) == [
        ("unknown_number", f"£1{NB}251{NB}198")
    ]


def test_checker_grouped_display_of_another_figure_is_wrong_reference(
    figure_list: list[Figure],
) -> None:
    assert kinds(f"Revenue reached 1{NB}200 [F3].", figure_list) == [
        ("wrong_reference", f"1{NB}200")
    ]


def test_checker_plain_space_splits_the_number(figure_list: list[Figure]) -> None:
    result = kinds("Revenue reached £1 251 199 [F3].", figure_list)
    assert len(result) >= 2
    assert ("missing_reference", "£1") in result
    assert ("unknown_number", "199") in result


def test_checker_nb_space_after_marker_splits_the_number(
    figure_list: list[Figure],
) -> None:
    result = kinds(f"Revenue reached £1 [F3]{NB}251{NB}199.", figure_list)
    assert ("unknown_number", "£1") in result
    assert ("missing_reference", f"251{NB}199") in result


@pytest.mark.parametrize(
    "bad", [f"£1{NB}23", f"£1{NB}2345", f"£12{NB}34", f"£1{NB}251{NB}19", f"£{NB}251"]
)
def test_checker_rejects_bad_grouping(bad: str, figure_list: list[Figure]) -> None:
    assert check_narrative(f"Revenue reached {bad} [F3].", figure_list)


def test_checker_ascii_space_variant_of_count_is_rejected(
    figure_list: list[Figure],
) -> None:
    assert check_narrative("There were 1 200 [F4] orders.", figure_list)


def run_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replies: list[str | Exception]
) -> tuple[Path, FakeLLM, FakeGmail]:
    llm, gmail = install(monkeypatch, FakeLLM(replies))
    out = tmp_path / "out"
    run_week(cleaned(ROWS_B, BIG), START, "f.xlsx", out, False, Budget(cap_usd=5.0))
    return out / WEEK, llm, gmail


def figures_json(folder: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((folder / "figures.json").read_text())
    return data


def test_render_restores_ok_after_a_bad_then_restored_narrative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, _, _ = run_saved(tmp_path, monkeypatch, [GOOD])
    assert figures_json(folder)["status"] == "ok"
    original = (folder / "narrative.json").read_text()
    (folder / "narrative.json").write_text(BAD)
    assert main(["render", "--from", str(folder)]) == 2
    broken = figures_json(folder)
    assert broken["status"] == "needs_review"
    assert broken["reasons"] == ["narrative failed number check on re-render"]
    assert [v["kind"] for v in broken["violations"]] == ["unknown_number"]
    assert "Narrative withheld" in (folder / "report.md").read_text()
    (folder / "narrative.json").write_text(original)
    assert main(["render", "--from", str(folder)]) == 0
    restored = figures_json(folder)
    assert (restored["status"], restored["reasons"], restored["violations"]) == (
        "ok",
        [],
        [],
    )
    assert (
        f"Revenue reached £1{NB}251{NB}199 [F3]" in (folder / "report.md").read_text()
    )


def test_render_fails_twice_keeps_one_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, _, _ = run_saved(tmp_path, monkeypatch, [GOOD])
    (folder / "narrative.json").write_text(
        narrative("Revenue reached £1,251,199 [F3]", "Orders were steady.")
    )
    assert main(["render", "--from", str(folder)]) == 2
    assert main(["render", "--from", str(folder)]) == 2
    assert figures_json(folder)["reasons"] == [
        "narrative failed number check on re-render"
    ]


def test_render_draft_failure_adds_reason_and_exit_2_then_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, _, _ = run_saved(tmp_path, monkeypatch, [GOOD])
    attempts: list[str] = []

    def failing(to: str, subject: str, html: str, service: Any | None = None) -> str:
        attempts.append(subject)
        raise RuntimeError("secret provider body")

    monkeypatch.setattr("weekly_kpi_report_agent.gmail.create_draft", failing)
    assert main(["render", "--from", str(folder), "--draft"]) == 2
    data = figures_json(folder)
    assert data["status"] == "needs_review"
    assert data["reasons"] == ["gmail draft failed: RuntimeError"]
    assert data["draft_id"] is None
    assert "secret provider body" not in json.dumps(data)
    assert len(attempts) == 1
    assert (
        "The Gmail draft could not be created (RuntimeError)"
        in (folder / "report.html").read_text()
    )

    gmail = FakeGmail()
    monkeypatch.setattr("weekly_kpi_report_agent.gmail.create_draft", gmail)
    assert main(["render", "--from", str(folder), "--draft"]) == 0
    data = figures_json(folder)
    assert (data["status"], data["reasons"], data["draft_id"]) == ("ok", [], "draft-1")
    assert [s for _, s in gmail.calls] == ["Weekly sales KPIs — week of 2011-11-28"]


def test_render_without_draft_flag_never_calls_gmail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, _, gmail = run_saved(tmp_path, monkeypatch, [GOOD])
    assert main(["render", "--from", str(folder)]) == 0
    assert gmail.calls == []


def no_data_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, FakeGmail]:
    _, gmail = install(monkeypatch, FakeLLM([GOOD]))
    out = tmp_path / "out"
    week = run_week(
        cleaned(ROWS_B, BIG),
        date(2011, 10, 3),
        "f.xlsx",
        out,
        False,
        Budget(cap_usd=5.0),
    )
    assert week.status == "no_data"
    return out / "2011-10-03", gmail


def test_render_no_data_stays_no_data_with_no_draft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, gmail = no_data_folder(tmp_path, monkeypatch)
    assert main(["render", "--from", str(folder), "--draft"]) == 3
    assert gmail.calls == []
    data = figures_json(folder)
    assert (data["status"], data["draft_id"]) == ("no_data", None)


def test_render_no_data_with_stray_narrative_stays_no_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, gmail = no_data_folder(tmp_path, monkeypatch)
    (folder / "narrative.json").write_text(
        narrative("Weekly sales summary", "The figures for the week are below.")
    )
    assert main(["render", "--from", str(folder), "--draft"]) == 3
    assert gmail.calls == []
    assert figures_json(folder)["status"] == "no_data"


def test_render_invalid_narrative_json_exits_1_and_rewrites_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    folder, _, gmail = run_saved(tmp_path, monkeypatch, [GOOD])
    for bad in ["not json", json.dumps({"headline": "x"}), "[]", ""]:
        (folder / "narrative.json").write_text(bad)
        before = (folder / "figures.json").read_text()
        md = (folder / "report.md").read_text()
        assert main(["render", "--from", str(folder), "--draft"]) == 1
        assert f"error: invalid narrative.json in {folder}" in capsys.readouterr().err
        assert (folder / "figures.json").read_text() == before
        assert (folder / "report.md").read_text() == md
    assert gmail.calls == []


def test_render_never_calls_the_llm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, _, _ = run_saved(tmp_path, monkeypatch, [GOOD])
    calls: list[tuple[str, str]] = []

    def boom(system: str, user: str) -> LLMReply:
        calls.append((system, user))
        raise AssertionError("llm called during render")

    monkeypatch.setattr("weekly_kpi_report_agent.llm.complete", boom)
    gmail = FakeGmail()
    monkeypatch.setattr("weekly_kpi_report_agent.gmail.create_draft", gmail)
    narrative_file = folder / "narrative.json"
    good = narrative_file.read_text()
    assert main(["render", "--from", str(folder)]) == 0
    assert main(["render", "--from", str(folder), "--draft"]) == 0
    narrative_file.write_text(BAD)
    assert main(["render", "--from", str(folder)]) == 2
    narrative_file.write_text("garbage")
    assert main(["render", "--from", str(folder)]) == 1
    narrative_file.unlink()
    assert main(["render", "--from", str(folder)]) == 2
    narrative_file.write_text(good)
    assert main(["render", "--from", str(folder)]) == 0
    assert calls == []


def test_render_without_narrative_keeps_saved_state_figures_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, _, _ = run_saved(tmp_path, monkeypatch, [GOOD])
    (folder / "narrative.json").unlink()
    assert main(["render", "--from", str(folder)]) == 2
    assert "Narrative withheld" in (folder / "report.md").read_text()


@pytest.mark.parametrize(
    "replies",
    [
        [BAD, BAD, BAD],
        ["not json", "not json", "not json"],
        [RuntimeError("down")],
    ],
    ids=["checker", "schema", "model-error"],
)
def test_stale_narrative_json_is_deleted_by_a_later_failing_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replies: list[str | Exception]
) -> None:
    folder, _, _ = run_saved(tmp_path, monkeypatch, [GOOD])
    assert (folder / "narrative.json").exists()
    install(monkeypatch, FakeLLM(replies))
    week = run_week(
        cleaned(ROWS_B, BIG),
        START,
        "f.xlsx",
        tmp_path / "out",
        False,
        Budget(cap_usd=5.0),
    )
    assert week.status == "needs_review"
    assert not (folder / "narrative.json").exists()
    assert main(["render", "--from", str(folder)]) == 2


def test_stale_narrative_json_is_deleted_when_cost_cap_blocks_the_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, _, _ = run_saved(tmp_path, monkeypatch, [GOOD])
    llm, _ = install(monkeypatch, FakeLLM([GOOD]))
    run_week(
        cleaned(ROWS_B, BIG),
        START,
        "f.xlsx",
        tmp_path / "out",
        False,
        Budget(cap_usd=0.0001, spent_usd=1.0),
    )
    assert llm.calls == []
    assert not (folder / "narrative.json").exists()


def test_narrative_json_is_not_written_when_none_passed_and_is_valid_when_one_did(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, _, _ = run_saved(tmp_path, monkeypatch, [BAD, BAD, BAD])
    assert not (folder / "narrative.json").exists()
    folder, _, _ = run_saved(tmp_path, monkeypatch, [BAD, GOOD])
    assert json.loads((folder / "narrative.json").read_text()) == json.loads(GOOD)


def test_stale_narrative_json_removed_by_cli_run_with_failing_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    book = write_book(tmp_path / "d.xlsx", ROWS_B, BIG)
    out = tmp_path / "out"
    args = [
        "run",
        "--data",
        str(book),
        "--as-of",
        "2011-12-05",
        "--out",
        str(out),
        "--no-gmail",
    ]
    install(monkeypatch, FakeLLM([GOOD]))
    assert main(args) == 0
    assert (out / WEEK / "narrative.json").exists()
    install(monkeypatch, FakeLLM([BAD]))
    assert main(args) == 2
    assert not (out / WEEK / "narrative.json").exists()
