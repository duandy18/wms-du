#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Pattern

ALLOW_EXT: set[str] = {".py", ".pyi", ".toml", ".yaml", ".yml", ".json", ".md"}
FULLWIDTH_OR_CJK: Pattern[str] = re.compile(
    r"[\u3000-\u303F\uFF00-\uFFEF\u4E00-\u9FFF]"
)


def check(path: Path) -> list[tuple[int, str]]:
    bad: list[tuple[int, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return bad
    for i, line in enumerate(text.splitlines(), 1):
        if FULLWIDTH_OR_CJK.search(line):
            bad.append((i, line))
    return bad


def main() -> int:
    failed = False
    for arg in sys.argv[1:]:
        p = Path(arg)
        if p.suffix not in ALLOW_EXT:
            continue
        if str(p).startswith(("docs/", "canvas/", "assets/")):
            continue
        hits = check(p)
        if hits:
            failed = True
            print(f"[NON-ASCII BLOCKED] {p}")
            for ln, content in hits[:5]:
                print(f"  L{ln}: {content}")
            if len(hits) > 5:
                print(f"  ... and {len(hits) - 5} more lines.")
    if failed:
        print(
            "\n❌ Found full-width/CJK characters in code. Use English & half-width only."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
