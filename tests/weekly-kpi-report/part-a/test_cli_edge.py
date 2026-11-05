import csv
import io
import urllib.error
from datetime import date
from pathlib import Path
from typing import Any, Self

import pandas as pd
import pytest
from edge_support import (
    GOOD,
    NO_NUMBERS,
    ROWS_A,
    ROWS_B,
    ROWS_C,
    WEEK_A,
    WEEK_B,
    WEEK_C,
    WRONG,
    FakeLLM,
    install,
    saved,
    write_book,
)

from weekly_kpi_report_agent import download
from weekly_kpi_report_agent.cli import main, weeks
from weekly_kpi_report_agent.data import COLUMNS


def book(tmp_path: Path, *groups: list[tuple[Any, ...]]) -> Path:
    return write_book(tmp_path / "d.xlsx", *(groups or (ROWS_A, ROWS_B, ROWS_C)))


def run(book_path: Path, out: Path, *extra: str, as_of: str = "2011-12-05") -> int:
    return main(
        ["run", "--data", str(book_path), "--as-of", as_of, "--out", str(out), *extra]
    )


def test_exit_code_0_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    llm, gmail = install(monkeypatch, FakeLLM([GOOD]))
    assert run(book(tmp_path), tmp_path / "out") == 0
    assert len(llm.calls) == 1
    assert [subject for _, subject in gmail.calls] == [
        "Weekly sales KPIs — week of 2011-11-28"
    ]


def test_exit_code_2_needs_review_and_prefixed_subject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, gmail = install(monkeypatch, FakeLLM(["not json"]))
    assert run(book(tmp_path), tmp_path / "out") == 2
    assert [subject for _, subject in gmail.calls] == [
        "[NEEDS REVIEW] Weekly sales KPIs — week of 2011-11-28"
    ]


def test_exit_code_3_no_data_calls_nothing_but_writes_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm, gmail = install(monkeypatch, FakeLLM([GOOD]))
    assert run(book(tmp_path), tmp_path / "out", as_of="2011-12-12") == 3
    assert llm.calls == []
    assert gmail.calls == []
    assert saved(tmp_path / "out", "2011-12-05")["status"] == "no_data"
    assert (
        "No sales data for week 2011-12-05"
        in (tmp_path / "out" / "2011-12-05" / "report.md").read_text()
    )


def test_exit_code_1_for_missing_file_and_no_output_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    llm, gmail = install(monkeypatch, FakeLLM([GOOD]))
    assert run(tmp_path / "missing.xlsx", tmp_path / "out") == 1
    err = capsys.readouterr().err
    assert "error:" in err
    assert str(tmp_path) not in err
    assert not (tmp_path / "out").exists()
    assert llm.calls == [] and gmail.calls == []


def test_exit_code_1_for_unreadable_workbook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch, FakeLLM([GOOD]))
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"this is not a zip file")
    notebook = tmp_path / "notes.txt"
    notebook.write_text("hello")
    assert run(bad, tmp_path / "out") == 1
    assert run(notebook, tmp_path / "out") == 1
    assert not (tmp_path / "out").exists()


def test_missing_columns_are_listed_in_canonical_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    install(monkeypatch, FakeLLM([GOOD]))
    frame = pd.DataFrame([ROWS_C[0]], columns=COLUMNS).drop(
        columns=["Country", "Price", "Invoice"]
    )
    path = tmp_path / "d.xlsx"
    frame.to_excel(path, index=False)
    assert run(path, tmp_path / "out") == 1
    assert "missing columns: Invoice, Price, Country" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_header_only_workbook_is_no_data_not_a_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm, _ = install(monkeypatch, FakeLLM([GOOD]))
    path = tmp_path / "empty.xlsx"
    pd.DataFrame(columns=COLUMNS).to_excel(path, index=False)
    assert run(path, tmp_path / "out") == 3
    assert llm.calls == []


def test_extra_columns_and_shuffled_column_order_are_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch, FakeLLM([GOOD]))
    frame = pd.DataFrame(ROWS_C, columns=COLUMNS)
    frame["Notes"] = "x"
    path = tmp_path / "d.xlsx"
    frame[["Notes", *reversed(COLUMNS)]].to_excel(path, index=False)
    assert run(path, tmp_path / "out") == 0


class FixedDate(date):
    @classmethod
    def today(cls) -> Self:
        return cls(2011, 12, 7)


@pytest.mark.parametrize(
    ("today", "week"),
    [
        ("2011-12-07", WEEK_C),
        ("2011-12-05", WEEK_C),
        ("2011-12-04", WEEK_B),
        ("2011-11-27", WEEK_A),
        ("2011-11-21", WEEK_A),
    ],
)
def test_run_defaults_as_of_to_today(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, today: str, week: str
) -> None:
    install(monkeypatch, FakeLLM([NO_NUMBERS]))
    y, m, d = (int(p) for p in today.split("-"))

    class Today(FixedDate):
        @classmethod
        def today(cls) -> Self:
            return cls(y, m, d)

    monkeypatch.setattr("weekly_kpi_report_agent.cli.date", Today)
    out = tmp_path / "out"
    assert main(["run", "--data", str(book(tmp_path)), "--out", str(out)]) == 0
    assert [p.name for p in out.iterdir()] == [week]


def test_explicit_as_of_beats_the_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch, FakeLLM([NO_NUMBERS]))
    monkeypatch.setattr("weekly_kpi_report_agent.cli.date", FixedDate)
    out = tmp_path / "out"
    assert run(book(tmp_path), out, as_of="2011-11-22") == 0
    assert [p.name for p in out.iterdir()] == [WEEK_A]


@pytest.mark.parametrize(
    ("as_of", "week"),
    [
        ("2011-12-11", WEEK_C),
        ("2011-12-12", "2011-12-05"),
        ("2011-12-06", WEEK_C),
    ],
)
def test_as_of_picks_the_latest_week_whose_sunday_is_before_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, as_of: str, week: str
) -> None:
    install(monkeypatch, FakeLLM([NO_NUMBERS]))
    out = tmp_path / "out"
    run(book(tmp_path), out, as_of=as_of)
    assert [p.name for p in out.iterdir()] == [week]


def test_report_recipient_comes_from_env_with_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, gmail = install(monkeypatch, FakeLLM([NO_NUMBERS]))
    monkeypatch.delenv("KPI_REPORT_TO", raising=False)
    run(book(tmp_path), tmp_path / "a")
    monkeypatch.setenv("KPI_REPORT_TO", "boss@example.com")
    run(book(tmp_path), tmp_path / "b")
    assert [to for to, _ in gmail.calls] == ["modis0001@gmail.com", "boss@example.com"]


def test_no_gmail_flag_still_writes_files_and_keeps_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, gmail = install(monkeypatch, FakeLLM(["not json"]))
    assert run(book(tmp_path), tmp_path / "out", "--no-gmail") == 2
    assert gmail.calls == []
    assert saved(tmp_path / "out")["draft_id"] is None


def read_summary(out: Path) -> list[dict[str, str]]:
    with (out / "backfill_summary.csv").open(newline="") as fh:
        return list(csv.DictReader(fh))


def backfill(book_path: Path, out: Path, first: str, last: str) -> int:
    return main(
        [
            "backfill",
            "--data",
            str(book_path),
            "--from",
            first,
            "--to",
            last,
            "--out",
            str(out),
        ]
    )


def test_backfill_cap_is_shared_across_weeks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm, gmail = install(
        monkeypatch, FakeLLM(["not json"], input_tokens=1_000_000, output_tokens=0)
    )
    monkeypatch.setenv("KPI_COST_CAP_USD", "3")
    out = tmp_path / "out"
    assert backfill(book(tmp_path, ROWS_A, ROWS_C), out, WEEK_A, WEEK_C) == 0
    assert len(llm.calls) == 2
    assert gmail.calls == []
    rows = read_summary(out)
    assert [(r["week_start"], r["status"], r["attempts"]) for r in rows] == [
        (WEEK_A, "needs_review", "2"),
        (WEEK_B, "no_data", "0"),
        (WEEK_C, "needs_review", "0"),
    ]
    assert rows[0]["reasons"] == "model output invalid; cost cap reached"
    assert rows[2]["reasons"] == "cost cap reached"
    assert saved(out, WEEK_C)["attempts"] == 0


def test_backfill_cap_zero_means_zero_calls_in_every_week(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm, _ = install(monkeypatch, FakeLLM([GOOD]))
    monkeypatch.setenv("KPI_COST_CAP_USD", "0")
    out = tmp_path / "out"
    assert backfill(book(tmp_path), out, WEEK_A, WEEK_C) == 0
    assert llm.calls == []
    assert {r["reasons"] for r in read_summary(out)} == {"cost cap reached"}


def test_backfill_without_cap_pressure_spends_per_week_and_counts_violations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm, _ = install(monkeypatch, FakeLLM([WRONG]))
    out = tmp_path / "out"
    assert backfill(book(tmp_path), out, WEEK_A, WEEK_C) == 0
    assert len(llm.calls) == 9
    rows = read_summary(out)
    assert [(r["attempts"], r["violations"]) for r in rows] == [("3", "1")] * 3
    assert rows[0]["reasons"] == "narrative failed number check after 3 attempts"


def test_backfill_snaps_mid_week_dates_to_whole_weeks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch, FakeLLM([NO_NUMBERS]))
    out = tmp_path / "out"
    assert backfill(book(tmp_path), out, "2011-11-16", "2011-11-30") == 0
    assert [r["week_start"] for r in read_summary(out)] == [WEEK_A, WEEK_B, WEEK_C]


def test_backfill_single_day_range_is_one_week(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch, FakeLLM([NO_NUMBERS]))
    out = tmp_path / "out"
    assert backfill(book(tmp_path), out, "2011-11-23", "2011-11-23") == 0
    assert [r["week_start"] for r in read_summary(out)] == [WEEK_B]


def test_backfill_range_ending_before_its_first_week_has_only_the_header(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm, _ = install(monkeypatch, FakeLLM([GOOD]))
    out = tmp_path / "out"
    assert backfill(book(tmp_path), out, "2011-11-28", "2011-11-01") == 0
    assert (out / "backfill_summary.csv").read_text().strip() == (
        "week_start,status,attempts,violations,reasons"
    )
    assert llm.calls == []
    assert weeks(date(2011, 11, 28), date(2011, 11, 27)) == []


def test_backfill_bad_input_exits_1_without_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch, FakeLLM([GOOD]))
    out = tmp_path / "out"
    assert backfill(tmp_path / "missing.xlsx", out, WEEK_A, WEEK_C) == 1
    assert not out.exists()


def test_eval_checker_never_calls_the_llm_and_exit_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm, gmail = install(monkeypatch, FakeLLM([GOOD]))
    out = tmp_path / "out"
    code = main(
        [
            "eval-checker",
            "--data",
            str(book(tmp_path)),
            "--from",
            WEEK_B,
            "--to",
            WEEK_C,
            "--out",
            str(out),
        ]
    )
    assert code == 0
    assert llm.calls == [] and gmail.calls == []
    assert (out / "checker_eval.json").exists()
    assert (
        main(
            [
                "eval-checker",
                "--data",
                str(tmp_path / "missing.xlsx"),
                "--from",
                WEEK_B,
                "--to",
                WEEK_C,
                "--out",
                str(tmp_path / "out2"),
            ]
        )
        == 1
    )
    assert not (tmp_path / "out2").exists()


class BrokenResponse:
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        raise ConnectionResetError("peer reset secret-detail")


@pytest.mark.parametrize(
    "failure",
    [
        urllib.error.URLError("no route secret-detail"),
        TimeoutError("timed out secret-detail"),
        ConnectionResetError("reset secret-detail"),
        OSError("disk secret-detail"),
    ],
)
def test_download_network_error_exits_1_and_leaves_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: OSError,
) -> None:
    def boom(url: str, timeout: float | None = None) -> Any:
        raise failure

    monkeypatch.setattr("weekly_kpi_report_agent.download.urllib.request.urlopen", boom)
    dest = tmp_path / "raw"
    assert main(["download", "--dest", str(dest)]) == 1
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "secret-detail" not in captured.err + captured.out
    assert list(tmp_path.rglob("*")) == []


def test_download_failure_while_reading_the_body_leaves_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "weekly_kpi_report_agent.download.urllib.request.urlopen",
        lambda url, timeout=None: BrokenResponse(),
    )
    assert main(["download", "--dest", str(tmp_path / "raw")]) == 1
    assert "secret-detail" not in capsys.readouterr().err
    assert list(tmp_path.rglob("*")) == []


def test_download_requests_the_pinned_url_with_a_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[str, float | None]] = []

    def fake(url: str, timeout: float | None = None) -> io.BytesIO:
        seen.append((url, timeout))
        return io.BytesIO(b"wrong bytes")

    monkeypatch.setattr("weekly_kpi_report_agent.download.urllib.request.urlopen", fake)
    assert main(["download", "--dest", str(tmp_path / "raw")]) == 1
    assert seen == [(download.URL, 120)]


def test_download_checksum_mismatch_keeps_an_existing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "raw"
    dest.mkdir()
    existing = dest / download.FILE_NAME
    existing.write_bytes(b"previous good copy")
    monkeypatch.setattr(
        "weekly_kpi_report_agent.download.urllib.request.urlopen",
        lambda url, timeout=None: io.BytesIO(b"tampered"),
    )
    assert main(["download", "--dest", str(dest)]) == 1
    assert [p.name for p in dest.iterdir()] == [download.FILE_NAME]
    assert existing.read_bytes() == b"previous good copy"


def test_auth_prints_the_token_path_and_exits_0(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    token = tmp_path / "token.json"
    monkeypatch.setattr("weekly_kpi_report_agent.cli.gmail.authorize", lambda: token)
    assert main(["auth"]) == 0
    assert str(token) in capsys.readouterr().out
