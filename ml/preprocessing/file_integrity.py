from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: str | Path, *, normalize_csv_line_endings: bool = False) -> str:
    """Hash exact bytes, or canonicalize CSV newlines when requested."""
    file_path = Path(path)
    digest = hashlib.sha256()
    with file_path.open("rb") as source:
        pending_carriage_return = b""
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            if not normalize_csv_line_endings or file_path.suffix.lower() != ".csv":
                digest.update(chunk)
                continue
            data = pending_carriage_return + chunk
            pending_carriage_return = b"\r" if data.endswith(b"\r") else b""
            if pending_carriage_return:
                data = data[:-1]
            digest.update(data.replace(b"\r\n", b"\n"))
        if pending_carriage_return:
            digest.update(pending_carriage_return)
    return digest.hexdigest()
