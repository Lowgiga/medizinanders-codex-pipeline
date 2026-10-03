from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import PipelineError


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def object_hash(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except (OSError, ValueError) as exc:
        raise PipelineError(f"Ungültige JSON-Datei {path}: {exc}") from exc


def write_json(path: Path, value: Any, *, exclusive: bool = False) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical(value)
    if exclusive:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise PipelineError(f"Unveränderliche Datei existiert bereits: {path}") from exc
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    else:
        temp = path.with_name(path.name + ".tmp")
        with temp.open("wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, path)


def contained(root: Path, relative: str, *, must_exist: bool = True) -> Path:
    root = root.resolve()
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root) or candidate == root:
        raise PipelineError(f"Pfad verlässt den erlaubten Projektordner: {relative}")
    if must_exist and not candidate.is_file():
        raise PipelineError(f"Datei fehlt: {candidate}")
    return candidate


def project_id(value: str) -> str:
    if not re.fullmatch(r"MA-\d{8}-\d{3}", value):
        raise PipelineError("Projekt-ID muss MA-YYYYMMDD-NNN entsprechen.")
    return value


def next_version(version: str, change: str = "minor") -> str:
    major, minor, patch = map(int, version.split("."))
    if change == "major":
        return f"{major + 1}.0.0"
    if change == "patch":
        return f"{major}.{minor}.{patch + 1}"
    return f"{major}.{minor + 1}.0"
