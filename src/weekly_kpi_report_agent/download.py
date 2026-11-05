import hashlib
import io
import urllib.request
import zipfile
from pathlib import Path

URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
SHA256 = "572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb"
FILE_NAME = "online_retail_II.xlsx"


class ChecksumError(ValueError):
    pass


def download(dest: Path) -> Path:
    with urllib.request.urlopen(URL, timeout=120) as response:
        payload: bytes = response.read()
    if hashlib.sha256(payload).hexdigest() != SHA256:
        raise ChecksumError(SHA256)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        content = archive.read(FILE_NAME)
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / FILE_NAME
    target.write_bytes(content)
    return target
