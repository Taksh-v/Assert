#!/usr/bin/env python3
"""Lightweight repo secret scanner.

This is intentionally conservative: it flags obvious credential-like tokens
in `.env`-style files and exits non-zero when found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


SECRET_PATTERNS = [
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password)\b\s*=\s*.+"),
    re.compile(r"(?i)\b(xox[baprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9-]{10,}|gh[pousr]_[A-Za-z0-9]{10,})\b"),
]


def scan_file(path: Path) -> list[str]:
    findings: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return findings

    for i, line in enumerate(text.splitlines(), start=1):
        for pattern in SECRET_PATTERNS:
            if pattern.search(line):
                findings.append(f"{path}:{i}: potential secret-like value")
                break
    return findings


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    targets = [root / ".env", root / ".env.example"]
    findings: list[str] = []

    for target in targets:
        if target.exists():
            findings.extend(scan_file(target))

    if findings:
        print("Secret scan found potential issues:")
        for item in findings:
            print(item)
        return 1

    print("Secret scan passed: no obvious credential-like values found in env files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
