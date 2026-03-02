from __future__ import annotations

from pathlib import Path

FILES = [
    Path("tests/quick/test_inbound_pick_count_v2.py"),
    Path("tests/quick/test_inbound_reclassify_v2.py"),
    Path("tests/quick/test_outbound_pg.py"),
    Path("tests/quick/test_outbound_core_v2.py"),
    Path("tests/quick/test_outbound_commit_v2.py"),
    Path("tests/services/test_order_outbound_flow_v3.py"),
]

def backup(p: Path, suffix: str) -> Path:
    bak = p.with_suffix(p.suffix + suffix)
    bak.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    return bak

def patch_file(p: Path) -> bool:
    if not p.exists():
        return False
    s = p.read_text(encoding="utf-8")
    orig = s

    # 止血：去掉不存在的 lot_id_key 相关条件（改成可执行的 SQL）
    s = s.replace("AND lot_id_key = 0", "AND lot_id IS NULL")
    s = s.replace("AND sl.lot_id_key = 0", "AND sl.lot_id IS NULL")
    s = s.replace("WHEN sl.lot_id_key = 0 THEN NULL", "WHEN sl.lot_id IS NULL THEN NULL")

    if s != orig:
        bak = backup(p, ".bak_fix")
        p.write_text(s, encoding="utf-8")
        print(f"[patched] {p} (backup: {bak})")
        return True

    print(f"[skip] {p} (no change)")
    return False

def main() -> None:
    n = 0
    for p in FILES:
        if patch_file(p):
            n += 1
    print(f"[done] patched_files={n}. Review with: git diff")

if __name__ == "__main__":
    main()
