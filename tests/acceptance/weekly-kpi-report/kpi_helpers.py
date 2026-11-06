"""Shared helpers for the weekly-kpi-report acceptance tests (spec DEC-14 fixture, fakes for DEC-08 and DEC-10)."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

COLUMNS = [
    "Invoice",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
    "Price",
    "Customer ID",
    "Country",
]
UK = "United Kingdom"
HEART = "WHITE HANGING HEART T-LIGHT HOLDER"
CAKE = "REGENCY CAKESTAND 3 TIER"
BIRD = "ASSORTED COLOUR BIRD ORNAMENT"
NA = float("nan")


def d(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M")


L3: tuple[Any, ...] = (
    "581002",
    "22423",
    CAKE,
    4,
    d("2011-11-30 11:00"),
    12.75,
    13000,
    "France",
)
L12: tuple[Any, ...] = (
    "536400",
    "22423",
    CAKE,
    6,
    d("2010-12-01 09:00"),
    12.75,
    15000,
    UK,
)
LINES_2010_2011: list[tuple[Any, ...]] = [
    ("581001", "85123A", HEART, 10, d("2011-11-28 10:00"), 2.55, 12345, UK),
    ("581001", "22423", CAKE, 2, d("2011-11-28 10:00"), 12.75, 12345, UK),
    L3,
    L3,
    ("581002", "POST", "POSTAGE", 1, d("2011-11-30 11:00"), 18.00, 13000, "France"),
    ("581003", "84879", BIRD, 24, d("2011-12-01 12:00"), 1.69, NA, UK),
    ("C581004", "85123A", HEART, -2, d("2011-12-02 09:00"), 2.55, 12345, UK),
    ("581005", "22423", CAKE, 1, d("2011-12-02 10:00"), 0.00, 14000, UK),
    ("A581006", "B", "Adjust bad debt", 1, d("2011-12-02 11:00"), -100.00, NA, UK),
    ("580900", "85123A", HEART, 20, d("2011-11-22 10:00"), 2.55, 12345, UK),
    ("580901", "22423", CAKE, 4, d("2011-11-24 10:00"), 12.75, 12345, UK),
    L12,
    ("581100", "84879", BIRD, 12, d("2011-12-05 09:00"), 1.69, 12345, UK),
]


def write_workbook(
    path: Path,
    rename: dict[str, str] | None = None,
    drop: list[str] | None = None,
    extra: list[tuple[Any, ...]] | None = None,
) -> Path:
    sheets: dict[str, list[tuple[Any, ...]]] = {
        "Year 2009-2010": [L12],
        "Year 2010-2011": LINES_2010_2011 + (extra or []),
    }
    with pd.ExcelWriter(path) as writer:
        for name, rows in sheets.items():
            df = pd.DataFrame(rows, columns=COLUMNS)
            if rename:
                df["Description"] = df["Description"].replace(rename)
            if drop:
                df = df.drop(columns=drop)
            df.to_excel(writer, sheet_name=name, index=False)
    return path


def narrative(
    headline: str = "Weekly sales summary", paragraphs: list[str] | None = None
) -> str:
    return json.dumps(
        {
            "headline": headline,
            "paragraphs": paragraphs or ["The figures for the week are below."],
        }
    )


GOOD = narrative(
    "Revenue reached £143 [F3] in the week of 2011-11-28 [F1]",
    [
        'Revenue rose +39.8% [F11] week on week from 3 [F4] orders. "REGENCY CAKESTAND 3 TIER" led with £77 [F26].'
    ],
)
NO_NUMBERS = narrative()
WRONG = narrative("Weekly sales summary", ["Revenue reached £134 [F3] this week."])


class FakeLLM:
    def __init__(
        self,
        replies: list[str | Exception] | None = None,
        input_tokens: int = 1000,
        output_tokens: int = 300,
    ) -> None:
        self.replies = replies or [NO_NUMBERS]
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system: str, user: str) -> Any:
        from weekly_kpi_report_agent.llm import LLMReply

        self.calls.append((system, user))
        reply = self.replies[min(len(self.calls), len(self.replies)) - 1]
        if isinstance(reply, Exception):
            raise reply
        return LLMReply(
            text=reply, input_tokens=self.input_tokens, output_tokens=self.output_tokens
        )


class FakeGmail:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self, to: str, subject: str, html: str, service: Any | None = None
    ) -> str:
        self.calls.append({"to": to, "subject": subject, "html": html})
        if self.error:
            raise self.error
        return f"draft-{len(self.calls)}"


def install(
    monkeypatch: pytest.MonkeyPatch,
    llm: FakeLLM | None = None,
    gmail: FakeGmail | None = None,
) -> tuple[FakeLLM, FakeGmail]:
    llm = llm or FakeLLM()
    gmail = gmail or FakeGmail()
    monkeypatch.setattr("weekly_kpi_report_agent.llm.complete", llm)
    monkeypatch.setattr("weekly_kpi_report_agent.gmail.create_draft", gmail)
    return llm, gmail


def cli(*args: str) -> int:
    from weekly_kpi_report_agent.cli import main

    code: int = main(list(args))
    return code


def run_week(workbook: Path, out: Path, as_of: str = "2011-12-05", *extra: str) -> int:
    return cli(
        "run", "--data", str(workbook), "--as-of", as_of, "--out", str(out), *extra
    )


def report(out: Path, week: str = "2011-11-28") -> dict[str, Any]:
    data: dict[str, Any] = json.loads((out / week / "figures.json").read_text())
    return data


def figs(out: Path, week: str = "2011-11-28") -> dict[str, dict[str, Any]]:
    return {f["id"]: f for f in report(out, week)["figures"]}


def week_figures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    from weekly_kpi_report_agent.models import Figure

    install(monkeypatch)
    out = tmp_path / "out"
    run_week(write_workbook(tmp_path / "fixture.xlsx"), out, "2011-12-05", "--no-gmail")
    return [Figure.model_validate(f) for f in report(out)["figures"]]
