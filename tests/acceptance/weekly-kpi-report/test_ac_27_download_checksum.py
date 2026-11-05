"""AC-27 — Given the download response replaced by bytes whose SHA-256 differs from DEC-13, when download --dest <tmp>, then exit 1, stderr contains "checksum mismatch", and <tmp> has no .xlsx and no .zip."""

import io
from pathlib import Path
from typing import Any

import pytest
from kpi_helpers import cli


def test_ac_27_download_checksum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_urlopen(url: str, timeout: float | None = None, **_: Any) -> io.BytesIO:
        return io.BytesIO(b"not the dataset")

    monkeypatch.setattr(
        "weekly_kpi_report_agent.download.urllib.request.urlopen", fake_urlopen
    )
    code = cli("download", "--dest", str(tmp_path / "raw"))
    assert code == 1
    assert "checksum mismatch" in capsys.readouterr().err
    assert [p for p in tmp_path.rglob("*") if p.suffix in {".xlsx", ".zip"}] == []
