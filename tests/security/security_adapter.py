"""ADAPT: wire the kit's security tests (test_security.py) to this app. Owner-only, locked like tests/acceptance/.

Fill every function and constant marked ADAPT. A check that genuinely doesn't apply goes in NOT_APPLICABLE with
the reason; it then shows as skipped with that reason. Never use NOT_APPLICABLE to silence a failing check; a real hole the owner accepts
for now goes in KNOWN_OPEN (shows as xfail with the reason).
Check names: pii_logs, prompt_injection, model_output, step_skip, xff_spoof, cors, provider_error, body_cap, image_lock.
`make security` fails when a test listed in tests/security/EXPECTED_TESTS isn't collected by the full test run.
After adapting: uv run pytest tests/security --collect-only -q | grep '::' > tests/security/EXPECTED_TESTS
"""

import json
import os
import tempfile
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from starlette.testclient import TestClient

if TYPE_CHECKING:
    from kit_security import FakeLLM

REPO = Path(__file__).resolve().parents[2]

NOT_APPLICABLE: dict[str, str] = {
    "step_skip": "batch CLI job, no multi-step web workflow a caller could skip into",
    "xff_spoof": "no HTTP endpoint and no rate-limited route; the job runs locally on a schedule",
    "cors": "no HTTP endpoint, nothing is called from a browser",
    "body_cap": "no HTTP endpoint; dataset text fields are length-capped in code before they reach the model (spec AC)",
    "image_lock": "no deploy image: runs locally / cron example only, never deployed",
}
# A real hole the owner accepts for now (shows as xfail with the reason, listed in the PR). Fix it, then remove the entry.
KNOWN_OPEN: dict[str, str] = {}

RATE_LIMIT = 5  # ADAPT: requests one session may make to the rate-limited endpoint before it gets 429
CORS_PATH = "/ADAPT"  # ADAPT: a route browsers call cross-origin
ALLOWED_ORIGIN = "https://ADAPT.example"  # ADAPT: the one origin allowed to call it
BODY_CAP_PATH = "/ADAPT"  # ADAPT: a POST route that takes a JSON body
REQUEST_ID_HEADER = "x-request-id"
USER_INPUT_TAG = (
    r"week-data-[0-9a-f]{16}"  # regex: a fresh random tag per message (DEC-18)
)
# ADAPT: files that define deploy images, e.g. [REPO / "api" / "app.py"]
IMAGE_FILES: list[Path] = []


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
_writes: list[Any] = []


def _workbook(path: Path, text: str) -> None:
    import pandas as pd

    rows = [
        ("580900", "22423", text, 4, datetime(2011, 11, 22, 10), 12.75, 12345, text),
        ("581001", "22423", text, 2, datetime(2011, 11, 28, 10), 12.75, 12345, text),
        (
            "581002",
            "84879",
            "ASSORTED COLOUR BIRD ORNAMENT",
            24,
            datetime(2011, 11, 30, 11),
            1.69,
            13000,
            "France",
        ),
        (
            "581100",
            "84879",
            "ASSORTED COLOUR BIRD ORNAMENT",
            12,
            datetime(2011, 12, 5, 9),
            1.69,
            12345,
            "France",
        ),
    ]
    pd.DataFrame(rows, columns=COLUMNS).to_excel(
        path, sheet_name="Year 2010-2011", index=False
    )


def app() -> Any:
    """Test shim: POST /report {"text", "email"} runs one weekly report (week 2011-11-28) with text in every free-text
    field of the data (product description, country) and email as the draft recipient; returns report.md."""
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    async def report(request: Request) -> PlainTextResponse:
        from weekly_kpi_report_agent.cli import main

        body = await request.json()
        work = Path(tempfile.mkdtemp())
        _workbook(work / "data.xlsx", body["text"])
        previous = os.environ.get("KPI_REPORT_TO")
        os.environ["KPI_REPORT_TO"] = body["email"] or "ops@example.com"
        try:
            main(
                [
                    "run",
                    "--data",
                    str(work / "data.xlsx"),
                    "--as-of",
                    "2011-12-05",
                    "--out",
                    str(work / "out"),
                ]
            )
        finally:
            if previous is None:
                os.environ.pop("KPI_REPORT_TO", None)
            else:
                os.environ["KPI_REPORT_TO"] = previous
        week = work / "out" / "2011-11-28"
        reasons = json.loads((week / "figures.json").read_text())["reasons"]
        failed = any(r.startswith("model call failed") for r in reasons)
        return PlainTextResponse(
            (week / "report.md").read_text(),
            status_code=502 if failed else 200,
            headers={REQUEST_ID_HEADER: uuid.uuid4().hex},
        )

    return Starlette(routes=[Route("/report", report, methods=["POST"])])


def install_fakes(monkeypatch: pytest.MonkeyPatch, llm: "FakeLLM") -> None:
    """Routes llm.complete to llm.respond and gmail.create_draft to an in-memory recorder."""
    from weekly_kpi_report_agent.llm import LLMReply

    _writes.clear()

    def complete(system: str, user: str) -> Any:
        return LLMReply(
            text=llm.respond(system, user), input_tokens=100, output_tokens=50
        )

    def create_draft(
        to: str, subject: str, html: str, service: Any | None = None
    ) -> str:
        _writes.append({"to": to, "subject": subject})
        return f"draft-{len(_writes)}"

    monkeypatch.setattr("weekly_kpi_report_agent.llm.complete", complete)
    monkeypatch.setattr("weekly_kpi_report_agent.gmail.create_draft", create_draft)


def good_reply() -> Any:
    """A valid narrative (DEC-07) with no numbers, so it always passes the checker."""
    return json.dumps(
        {
            "headline": "Weekly sales summary",
            "paragraphs": ["The figures for the week are below."],
        }
    )


def invalid_reply(canary: str) -> Any:
    """Breaks the Narrative schema (extra key, paragraphs not a list) and carries the canary."""
    return json.dumps({"headline": canary, "paragraphs": canary, "extra": canary})


def provider_error(canary: str) -> Exception:
    return RuntimeError(f"provider 500: {canary}")


def send_visitor_text(http: TestClient, text: str, email: str) -> Any:
    return http.post("/report", json={"text": text, "email": email})


def skip_step(http: TestClient) -> Any:
    raise NotImplementedError("n/a: step_skip")


def writes() -> list[Any]:
    return _writes


def call_rate_limited(http: TestClient, headers: dict[str, str]) -> Any:
    raise NotImplementedError("n/a: xff_spoof")


def _break_gmail(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: Any, **kwargs: Any) -> str:
        raise RuntimeError("gmail 503 PII_CANARY")

    monkeypatch.setattr("weekly_kpi_report_agent.gmail.create_draft", fail)


BREAK_DEPENDENCY: dict[str, Callable[[pytest.MonkeyPatch], None]] = {
    "gmail": _break_gmail
}
