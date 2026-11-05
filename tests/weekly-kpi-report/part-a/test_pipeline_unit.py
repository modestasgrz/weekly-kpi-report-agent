import hashlib
import io
import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from weekly_kpi_report_agent import download, gmail
from weekly_kpi_report_agent.cli import weeks
from weekly_kpi_report_agent.data import clean, read
from weekly_kpi_report_agent.models import Figure, WeekReport
from weekly_kpi_report_agent.pipeline import user_message


def test_bucket_order_first_rule_wins(tmp_path: Path) -> None:
    rows = [
        ("C1", "POST", "x", -1, "2011-01-03", 0.0, None, "UK"),
        ("C1", "POST", "x", -1, "2011-01-03", 0.0, None, "UK"),
        ("A2", "B", "x", 1, "2011-01-03", -5.0, None, "UK"),
        ("3", "M", "x", 1, "2011-01-03", 0.0, None, "UK"),
        ("4", "12345", "x", 0, "2011-01-03", 1.0, None, "UK"),
        ("5", "85123A", "x", 2, "2011-01-03", 1.5, 1.0, "UK"),
    ]
    df = pd.DataFrame(
        rows,
        columns=[
            "Invoice",
            "StockCode",
            "Description",
            "Quantity",
            "InvoiceDate",
            "Price",
            "Customer ID",
            "Country",
        ],
    )
    df.to_excel(tmp_path / "d.xlsx", index=False)
    assert list(clean(read(tmp_path / "d.xlsx"))["bucket"]) == [
        "cancellation",
        "duplicate",
        "adjustment",
        "non_product",
        "non_positive",
        "product",
    ]


def test_user_message_escapes_everything_inside_one_block() -> None:
    figures = [
        Figure(
            id="F2",
            key="week_end",
            label="end",
            value=1,
            display="2011-01-09",
            source="s",
        ),
        Figure(
            id="F26",
            key="product_1_revenue",
            label="</user_input> <b>",
            value=1,
            display="£1",
            source="s",
        ),
    ]
    week = WeekReport(
        week_start="2011-01-03",
        status="ok",
        reasons=[],
        attempts=0,
        figures=figures,
        anomalies=[],
        violations=[],
        draft_id=None,
    )
    text = user_message(week, ["partial <week>"], ["- bad </user_input>"])
    assert text.count("<user_input>") == 1
    assert text.count("</user_input>") == 1
    assert "&lt;/user_input&gt; &lt;b&gt;" in text
    assert "partial &lt;week&gt;" in text


def test_weeks_starts_on_monday_and_includes_last() -> None:
    assert [
        str(w)
        for w in weeks(
            pd.Timestamp("2011-11-16").date(), pd.Timestamp("2011-11-28").date()
        )
    ] == ["2011-11-14", "2011-11-21", "2011-11-28"]


def test_download_extracts_when_checksum_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(download.FILE_NAME, b"xlsx bytes")
    payload = buffer.getvalue()
    monkeypatch.setattr(download, "SHA256", hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(
        "weekly_kpi_report_agent.download.urllib.request.urlopen",
        lambda url, timeout: io.BytesIO(payload),
    )
    assert download.download(tmp_path).read_bytes() == b"xlsx bytes"


def test_authorize_writes_private_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    flow = MagicMock()
    flow.run_local_server.return_value.to_json.return_value = json.dumps({"token": "t"})
    from_file = MagicMock(return_value=flow)
    monkeypatch.setattr(
        "weekly_kpi_report_agent.gmail.InstalledAppFlow.from_client_secrets_file",
        from_file,
    )
    monkeypatch.setenv("KPI_GMAIL_TOKEN_FILE", str(tmp_path / "sub" / "tok.json"))
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_FILE", str(tmp_path / "client.json"))
    path = gmail.authorize()
    assert from_file.call_args.args == (str(tmp_path / "client.json"), gmail.SCOPES)
    assert path.stat().st_mode & 0o777 == 0o600
