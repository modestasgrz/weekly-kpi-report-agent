import base64
import os
from collections.abc import Callable
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import httplib2
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_httplib2 import AuthorizedHttp
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]
DEFAULT_CLIENT_FILE = "~/.config/portfolio-demos/client_secret.json"
DEFAULT_AUTH_FILE = "~/.config/portfolio-demos/token-weekly-kpi-report.json"
DEFAULT_TO = "modis0001@gmail.com"
DRAFT_ERRORS = (
    HttpError,
    GoogleAuthError,
    httplib2.HttpLib2Error,
    OSError,
    ValueError,
    RuntimeError,
    KeyError,
)
HTTP_TIMEOUT_S = 30


def token_file() -> Path:
    return Path(os.environ.get("KPI_GMAIL_TOKEN_FILE", DEFAULT_AUTH_FILE)).expanduser()


def authorize() -> Path:
    client_file = Path(
        os.environ.get("GOOGLE_OAUTH_CLIENT_FILE", DEFAULT_CLIENT_FILE)
    ).expanduser()
    creds = InstalledAppFlow.from_client_secrets_file(
        str(client_file), SCOPES
    ).run_local_server(port=0)
    path = token_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(creds.to_json())
    path.chmod(0o600)
    return path


def create_draft(to: str, subject: str, html: str, service: Any | None = None) -> str:
    """Creates a Gmail draft. There is deliberately no send path: the token scope is gmail.compose and nothing here sends."""
    if service is None:
        load_credentials: Callable[..., Any] = Credentials.from_authorized_user_file
        creds = load_credentials(str(token_file()), SCOPES)
        if not creds.valid and creds.refresh_token:
            creds.refresh(Request())
            token_file().write_text(creds.to_json())
        service = build(
            "gmail",
            "v1",
            http=AuthorizedHttp(creds, http=httplib2.Http(timeout=HTTP_TIMEOUT_S)),
            cache_discovery=False,
        )
    message = MIMEText(html, "html", "utf-8")
    message["To"] = to
    message["Subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    draft: dict[str, Any] = (
        service.users()
        .drafts()
        .create(userId="me", body={"message": {"raw": raw}})
        .execute()
    )
    return str(draft["id"])
