import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from weekly_kpi_report_agent.data import COLUMNS, clean
from weekly_kpi_report_agent.llm import LLMReply

UK = "United Kingdom"
WEEK_A = "2011-11-14"
WEEK_B = "2011-11-21"
WEEK_C = "2011-11-28"
ROWS_A: list[tuple[Any, ...]] = [
    ("1", "10001", "AAA", 10, datetime(2011, 11, 14, 10), 2.5, 1.0, UK)
]
ROWS_B: list[tuple[Any, ...]] = [
    ("2", "10002", "BBB", 4, datetime(2011, 11, 22, 10), 12.5, 2.0, "France")
]
ROWS_C: list[tuple[Any, ...]] = [
    ("3", "10001", "AAA", 2, datetime(2011, 11, 29, 10), 12.5, 3.0, UK),
    ("4", "10002", "BBB", 1, datetime(2011, 12, 4, 12), 1.0, 4.0, UK),
]


def frame(*groups: list[tuple[Any, ...]]) -> pd.DataFrame:
    return pd.DataFrame([r for g in groups for r in g], columns=COLUMNS)


def cleaned(*groups: list[tuple[Any, ...]]) -> pd.DataFrame:
    return clean([frame(*groups)])


def write_book(path: Path, *groups: list[tuple[Any, ...]]) -> Path:
    frame(*groups).to_excel(path, index=False)
    return path


def narrative(headline: str, *paragraphs: str) -> str:
    return json.dumps({"headline": headline, "paragraphs": list(paragraphs)})


NO_NUMBERS = narrative("Weekly sales summary", "The figures for the week are below.")
GOOD = narrative("Revenue reached £26 [F3]", "There were 2 [F4] orders.")
WRONG = narrative("Weekly sales summary", "Revenue reached £134 [F3] this week.")


class FakeLLM:
    def __init__(
        self,
        replies: list[str | Exception],
        input_tokens: int = 100,
        output_tokens: int = 10,
    ) -> None:
        self.replies = replies
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system: str, user: str) -> LLMReply:
        self.calls.append((system, user))
        reply = self.replies[min(len(self.calls), len(self.replies)) - 1]
        if isinstance(reply, Exception):
            raise reply
        return LLMReply(
            text=reply, input_tokens=self.input_tokens, output_tokens=self.output_tokens
        )


class FakeGmail:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(
        self, to: str, subject: str, html: str, service: Any | None = None
    ) -> str:
        self.calls.append((to, subject))
        return f"draft-{len(self.calls)}"


def install(monkeypatch: pytest.MonkeyPatch, llm: FakeLLM) -> tuple[FakeLLM, FakeGmail]:
    gmail = FakeGmail()
    monkeypatch.setattr("weekly_kpi_report_agent.llm.complete", llm)
    monkeypatch.setattr("weekly_kpi_report_agent.gmail.create_draft", gmail)
    return llm, gmail


def saved(out: Path, week: str = WEEK_C) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((out / week / "figures.json").read_text())
    return data
