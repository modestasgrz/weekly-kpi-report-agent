"""AC-21 — gmail.SCOPES is exactly gmail.compose; create_draft with a mock service makes one users().drafts().create(userId="me", body={"message": {"raw": ...}}) call whose raw message has To, Subject and a text/html part; no file under src/ contains ".send(" or "gmail.send"."""

import base64
import email
from pathlib import Path
from unittest.mock import MagicMock

SRC = Path(__file__).resolve().parents[3] / "src"


def test_ac_21_gmail_draft_only() -> None:
    import weekly_kpi_report_agent.gmail

    gmail = weekly_kpi_report_agent.gmail

    assert gmail.SCOPES == ["https://www.googleapis.com/auth/gmail.compose"]
    service = MagicMock()
    service.users.return_value.drafts.return_value.create.return_value.execute.return_value = {
        "id": "d1"
    }
    gmail.create_draft("modis0001@gmail.com", "S", "<p>x</p>", service=service)
    create = service.users.return_value.drafts.return_value.create
    assert create.call_count == 1
    kwargs = create.call_args.kwargs
    assert kwargs["userId"] == "me"
    assert list(kwargs["body"]) == ["message"]
    assert list(kwargs["body"]["message"]) == ["raw"]
    msg = email.message_from_bytes(
        base64.urlsafe_b64decode(kwargs["body"]["message"]["raw"])
    )
    assert msg["To"] == "modis0001@gmail.com"
    assert msg["Subject"] == "S"
    assert any(part.get_content_type() == "text/html" for part in msg.walk())
    files = list(SRC.rglob("*.py"))
    assert len(files) > 1
    for p in files:
        text = p.read_text()
        assert ".send(" not in text, p
        assert "gmail.send" not in text, p
