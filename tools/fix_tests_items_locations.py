#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto-fix INSERTs in tests/ that violate current NOT NULL constraints:
- items: add `sku` when only (id, name) is inserted -> (id, sku, name)
- locations: ensure `code` and `name` columns exist in INSERT list

This is conservative: it only rewrites clearly-matching patterns.
Unknown shapes are skipped (printed as "SKIP").
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"

# Regex patterns (multiline-friendly but we process per line)
ITEMS_COLS_ID_NAME = re.compile(
    r"""(?P<prefix>INSERT\s+INTO\s+items\s*\()\s*
        (?P<cols>id\s*,\s*name)\s*
        (?P<mid>\)\s*VALUES\s*\()\s*
        (?P<vals>[^)]+?)\s*
        (?P<tail>\)\s*[^;]*;)""",
    re.IGNORECASE | re.VERBOSE,
)

# Capture id expression from VALUES(<id_expr>, <name_expr>)
ITEMS_EXTRACT_ID = re.compile(r"^\s*(?P<id_expr>[^,]+?)\s*,\s*(?P<name_expr>.+)$")

# locations: any INSERT missing `code` in column list
LOCATIONS_INSERT = re.compile(
    r"""(?P<prefix>INSERT\s+INTO\s+locations\s*\()\s*
        (?P<cols>[^)]*?)\s*
        (?P<mid>\)\s*VALUES\s*\()\s*
        (?P<vals>[^)]+?)\s*
        (?P<tail>\)\s*[^;]*;)""",
    re.IGNORECASE | re.VERBOSE,
)


def has_col(cols: str, name: str) -> bool:
    return any(c.strip().lower() == name for c in cols.split(","))


def parse_vals_list(vals: str):
    """Return list of top-level CSV values (no nested parens expected)."""
    parts = []
    depth = 0
    buf = []
    for ch in vals:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf).strip())
    return parts


def rewrite_items(line: str) -> str | None:
    m = ITEMS_COLS_ID_NAME.search(line)
    if not m:
        return None
    vals = m.group("vals")
    m_vals = ITEMS_EXTRACT_ID.match(vals)
    if not m_vals:
        # cannot parse safely
        return None
    id_expr = m_vals.group("id_expr").strip()
    name_expr = m_vals.group("name_expr").strip()

    new_cols = "id, sku, name"
    # Build 'SKU-' || <id_expr> safely for both literals and bind params
    new_vals = f"{id_expr}, 'SKU-' || {id_expr}, {name_expr}"

    return f"{m.group('prefix')}{new_cols}{m.group('mid')}{new_vals}{m.group('tail')}"


def rewrite_locations(line: str) -> str | None:
    m = LOCATIONS_INSERT.search(line)
    if not m:
        return None
    cols = m.group("cols")
    vals = m.group("vals")

    cols_list = [c.strip() for c in cols.split(",") if c.strip()]
    vals_list = parse_vals_list(vals)
    # columns and values count must match
    if len(cols_list) != len(vals_list):
        return None

    cols_lower = [c.lower() for c in cols_list]
    changed = False

    # Ensure 'name' exists (some tests use only id, warehouse_id, code/name)
    if "name" not in cols_lower:
        # append name with value = code or 'LOC-'||id
        # try to reuse code if exists
        name_val = None
        if "code" in cols_lower:
            name_val = vals_list[cols_lower.index("code")]
        elif "id" in cols_lower:
            name_val = f"'LOC-' || {vals_list[cols_lower.index('id')]}"
        else:
            # cannot infer safely
            return None
        cols_list.append("name")
        vals_list.append(name_val)
        cols_lower.append("name")
        changed = True

    # Ensure 'code' exists (your schema often needs code; earlier errors showed name, but we keep both safe)
    if "code" not in cols_lower:
        code_val = None
        if "name" in cols_lower:
            code_val = vals_list[cols_lower.index("name")]
        elif "id" in cols_lower:
            code_val = f"'LOC-' || {vals_list[cols_lower.index('id')]}"
        else:
            return None
        cols_list.append("code")
        vals_list.append(code_val)
        cols_lower.append("code")
        changed = True

    if not changed:
        return None

    new_cols = ", ".join(cols_list)
    new_vals = ", ".join(vals_list)
    return f"{m.group('prefix')}{new_cols}{m.group('mid')}{new_vals}{m.group('tail')}"


def process_file(path: Path) -> tuple[int, int]:
    """return (#items_changed, #locations_changed)"""
    text_in = path.read_text(encoding="utf-8")
    out = []
    items_c = locs_c = 0
    for line in text_in.splitlines(keepends=True):
        new_line = rewrite_items(line)
        if new_line:
            out.append(new_line)
            items_c += 1
            continue
        new_line = rewrite_locations(line)
        if new_line:
            out.append(new_line)
            locs_c += 1
            continue
        out.append(line)
    if items_c or locs_c:
        path.write_text("".join(out), encoding="utf-8")
    return items_c, locs_c


def main():
    total_i = total_l = 0
    files = sorted(TESTS_DIR.rglob("*.py"))
    for f in files:
        i, l = process_file(f)
        if i or l:
            print(f"[FIX] {f}: items={i}, locations={l}")
            total_i += i
            total_l += l
    print(f"Done. Rewritten items={total_i}, locations={total_l}")


if __name__ == "__main__":
    main()
