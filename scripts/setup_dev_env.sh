#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------
# Dev bootstrap: venv + dev deps + pre-commit + git template
# ---------------------------------------------

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "==> Working in: $ROOT_DIR"

# 1) Python & pip checks
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found. Please install Python 3.12+ first." >&2
  exit 1
fi
PYVER=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')
echo "==> Python: $PYVER"

# 2) Create/activate venv (.venv)
if [ ! -d ".venv" ]; then
  echo "==> Creating virtualenv at .venv"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
echo "==> Using venv: $(python -c 'import sys,site; print(sys.prefix)')"

python -m pip install -U pip

# 3) Install dev dependencies (pre-commit + linters/type checkers)
# Prefer requirements-dev.txt if present; otherwise install pinned minimal set
if [ -f "requirements-dev.txt" ]; then
  echo "==> Installing dev deps from requirements-dev.txt"
  pip install -r requirements-dev.txt
else
  echo "==> Installing dev deps (default set)"
  pip install \
    pre-commit==3.8.0 \
    ruff==0.6.9 \
    black==24.8.0 \
    isort==5.13.2 \
    mypy==1.11.1
fi

# 4) Ensure .pre-commit-config.yaml exists
if [ ! -f ".pre-commit-config.yaml" ]; then
  cat > .pre-commit-config.yaml <<'YAML'
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - id: ruff
        args: ["--fix", "--exit-non-zero-on-fix"]
      - id: ruff-format

  - repo: https://github.com/psf/black
    rev: 24.8.0
    hooks:
      - id: black
        args: ["--check"]

  - repo: https://github.com/pycqa/isort
    rev: 5.13.2
    hooks:
      - id: isort
        args: ["--check-only"]

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.11.1
    hooks:
      - id: mypy
        pass_filenames: false
        args: ["--config-file=pyproject.toml", "--exclude", "(^apps/)", "."]
        additional_dependencies:
          - fastapi
          - "pydantic>=2"
          - pydantic-settings
          - "SQLAlchemy>=2"
          - alembic
          - pytest

  - repo: local
    hooks:
      - id: forbid-non-ascii
        name: Forbid non-ASCII in code
        entry: python scripts/hooks/forbid_non_ascii.py
        language: system
        types_or: [python, pyi, yaml, toml, json, markdown]
        files: "^(app/|tests/|alembic/|config/|.github/)"
        exclude: "(^docs/|^README|^canvas/|^assets/)"
YAML
  echo "==> Wrote default .pre-commit-config.yaml"
fi

# 5) Ensure non-ASCII blocker script exists
if [ ! -f "scripts/hooks/forbid_non_ascii.py" ]; then
  mkdir -p scripts/hooks
  cat > scripts/hooks/forbid_non_ascii.py <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Pattern

ALLOW_EXT: set[str] = {".py", ".pyi", ".toml", ".yaml", ".yml", ".json", ".md"}
FULLWIDTH_OR_CJK: Pattern[str] = re.compile(r"[\u3000-\u303F\uFF00-\uFFEF\u4E00-\u9FFF]")

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
        print("\n❌ Found full-width/CJK characters in code. Use English & half-width only.")
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
PY
  chmod +x scripts/hooks/forbid_non_ascii.py
  echo "==> Wrote scripts/hooks/forbid_non_ascii.py"
fi

# 6) Commit message template
if [ ! -f ".gitmessage.txt" ]; then
  cat > .gitmessage.txt <<'TXT'
# Default commit message template
#
# Format: <type>(<scope>): <short summary>
# Types: feat, fix, chore, docs, style, refactor, test, ci, build
#
# Examples:
#   feat(users): add user ORM and Alembic migration
#   fix(auth): correct JWT expiration handling
#   chore(ci): enforce English-only checks in pre-commit
#   docs(readme): update setup instructions
#
# -------------------- Commit Message --------------------

TXT
  echo "==> Wrote .gitmessage.txt"
fi
git config commit.template .gitmessage.txt

# 7) Install pre-commit hook into .git/hooks/
pre-commit install
echo "==> pre-commit installed"

# 8) Optional: VS Code settings to highlight Unicode pitfalls
mkdir -p .vscode
if [ ! -f ".vscode/settings.json" ]; then
  cat > .vscode/settings.json <<'JSON'
{
  "files.autoGuessEncoding": true,
  "editor.unicodeHighlight.nonBasicASCII": true,
  "editor.unicodeHighlight.ambiguousCharacters": true,
  "editor.renderControlCharacters": true,
  "editor.renderWhitespace": "boundary",
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": { "source.fixAll.ruff": true },
  "files.eol": "\n",
  "editor.rulers": [100],
  "files.encoding": "utf8",
  "editor.defaultFormatter": "charliermarsh.ruff",
  "cSpell.enabled": false
}
JSON
  echo "==> Wrote .vscode/settings.json"
fi

echo "==> Done. Run: pre-commit run -a"
