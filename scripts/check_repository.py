#!/usr/bin/env python3
"""Prüft den Git-Dateisatz, ohne Produktionsdaten zu lesen oder zu veröffentlichen."""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {"README.md", "AGENTS.md", "CHANGELOG.md", "IMPLEMENTATION_CONTRACT.md", ".gitignore", "pyproject.toml", "requirements-lock.txt"}
DIRECTORIES = {"src", "tests", "scripts", "docs", "agents", "schemas", "templates", "config", "demo", ".github"}
FORBIDDEN_PARTS = {"projects", "production", "private", "sources", "workers", "inbox", "outbox", "freeze", "review", "handoff", "10_qa", "approvals", "attestations", "output", "generated"}
SUFFIXES = {".py", ".md", ".json", ".yaml", ".yml", ".toml", ".txt"}
SECRET = re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{24,}|github_pat_[A-Za-z0-9_]{40,}|sk-(?:proj-)?[A-Za-z0-9_-]{32,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")


def main():
    result = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True, check=True)
    files = sorted(set(p.decode("utf-8") for p in result.stdout.split(b"\0") if p))
    errors = []
    for name in files:
        path = Path(name)
        allowed = name in ROOT_FILES or (path.parts[0] in DIRECTORIES and (path.suffix in SUFFIXES or name == "scripts/ma"))
        if not allowed or set(path.parts) & FORBIDDEN_PARTS:
            errors.append(f"Nicht erlaubter Repository-Inhalt: {name}")
            continue
        if path.name.startswith(".env") or path.name in {"operator.yaml", "auth.json", "state.json", "events.jsonl"}:
            errors.append(f"Private Konfiguration: {name}")
        actual = ROOT / path
        if actual.is_symlink():
            errors.append(f"Symlink im Code-Dateisatz: {name}")
            continue
        try:
            data = actual.read_text(encoding="utf-8")
        except (UnicodeError, OSError):
            errors.append(f"Nicht lesbarer UTF-8-Code/Regeltext: {name}")
            continue
        if SECRET.search(data):
            errors.append(f"Möglicher echter Schlüssel in {name} (Wert wird nicht ausgegeben)")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Repository-Prüfung bestanden: {len(files)} erlaubte Textdateien; keine erkannten Schlüssel/Produktionsdateien.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
