# scripts/fix_alembic_cycle.py
import glob
import os
import re
import shutil
import sys

VERS_DIR = "app/db/migrations/versions"

# 目标revision与期望down_revision
FIXES = {
    "3a_fix_sqlite_inline_pks": "2a01baddb002",
    "1088800f816e": "3a_fix_sqlite_inline_pks",
}


def parse_heads():
    # 粗略解析所有文件头部，返回 {revision: (path, down_revision_raw)}
    ret = {}
    for p in glob.glob(os.path.join(VERS_DIR, "*.py")):
        with open(p, encoding="utf-8", errors="ignore") as f:
            txt = f.read()
        m_rev = re.search(r'^\s*revision\s*=\s*["\']([^"\']+)["\']\s*$', txt, re.M)
        if not m_rev:
            continue
        rev = m_rev.group(1)
        m_down = re.search(r"^\s*down_revision\s*=\s*(.+)$", txt, re.M)
        down = m_down.group(1).strip() if m_down else None
        ret[rev] = (p, down)
    return ret


def replace_down_revision(path, new_value):
    with open(path, encoding="utf-8", errors="ignore") as f:
        txt = f.read()
    # 兼容两种写法：down_revision = ... / down_revision: Union[...] = ...
    new_txt = re.sub(
        r"^\s*down_revision\s*[:=]\s*.*$",
        f'down_revision = "{new_value}"',
        txt,
        flags=re.M,
    )
    if new_txt != txt:
        shutil.copyfile(path, path + ".bak")
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_txt)
        return True
    return False


def main():
    if not os.path.isdir(VERS_DIR):
        print(f"❌ not found: {VERS_DIR}", file=sys.stderr)
        sys.exit(2)

    meta = parse_heads()
    changed = []
    missing = []

    for target_rev, want_down in FIXES.items():
        if target_rev not in meta:
            missing.append(target_rev)
            continue
        path, _down = meta[target_rev]
        if replace_down_revision(path, want_down):
            changed.append((target_rev, path, want_down))

    if missing:
        print("⚠️  not found in versions (by revision=...):", ", ".join(missing))

    if changed:
        print("✅ patched:")
        for rev, p, want in changed:
            print(f" - {rev} -> down_revision = {want}  ({p})")
    else:
        print("ℹ️  nothing changed; files may already be corrected.")

    print("\nNext steps:")
    print("  1) alembic heads -v   # 现在应该能列出真实 heads")
    print('  2) alembic revision --merge -m "merge parallel heads" <HEAD_A> <HEAD_B>')
    print("  3) 把 warehouses/locations 迁移的 down_revision 指向上一步生成的 merge 修订号")
    print("  4) alembic upgrade head && pytest -q -m smoke")


if __name__ == "__main__":
    main()
