#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 Alembic 中这几条 revision 强制线性化，剪掉 cycle。
改动仅限于各文件的 `down_revision` 一行，并为每个文件生成 .bak 备份。
"""
import os, io, re, glob, shutil, sys

VERS_DIR = "app/db/migrations/versions"

# 期望的线性拓扑（孩子: 父亲）
WANT = {
    "2a01baddb001": "31fc28eac057",
    "2a01baddb002": "2a01baddb001",
    "3a_fix_sqlite_inline_pks": "2a01baddb002",
    "1088800f816e": "3a_fix_sqlite_inline_pks",
    "1f9e5c2b8a11": "1088800f816e",
    "1223487447f9": "1f9e5c2b8a11",
    "bdc33e80391a": "1223487447f9",
    # 如果你的 31fc28eac057 是 merge 节点，通常它自己有 down_revision=(..., ...)，保持不动
}

REV_RE  = re.compile(r'^\s*revision\s*[:=]\s*[\'"]([^\'"]+)[\'"]\s*$', re.M)
DOWN_RE = re.compile(r'^\s*down_revision\s*[:=]\s*(.+)$', re.M)

def rewrite(path: str, new_parent: str) -> bool:
    txt = io.open(path, "r", encoding="utf-8", errors="ignore").read()
    if not DOWN_RE.search(txt):
        return False
    new_txt = DOWN_RE.sub(f'down_revision = "{new_parent}"', txt, count=1)
    if new_txt != txt:
        shutil.copyfile(path, path + ".bak")
        io.open(path, "w", encoding="utf-8").write(new_txt)
        return True
    return False

def main():
    if not os.path.isdir(VERS_DIR):
        print(f"❌ not found: {VERS_DIR}")
        sys.exit(2)

    # 建立 revision → 文件 路径索引（按内容里的 revision=… 找）
    rev2path = {}
    for p in glob.glob(os.path.join(VERS_DIR, "*.py")):
        try:
            txt = io.open(p, "r", encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        m = REV_RE.search(txt)
        if m:
            rev2path[m.group(1).strip()] = p

    changed = []
    missing = []
    for rev, parent in WANT.items():
        path = rev2path.get(rev)
        if not path:
            missing.append(rev)
            continue
        if rewrite(path, parent):
            changed.append((rev, parent, path))

    if changed:
        print("✅ changed down_revision:")
        for rev, parent, path in changed:
            print(f" - {rev}: down_revision = {parent}  ({path})")
    else:
        print("ℹ️ nothing changed; maybe already linearized.")

    if missing:
        print("⚠️ not found (no file with revision=...):", ", ".join(missing))

    print("\nNext:")
    print("  1) alembic heads -v   # 现在应能列出真实 head（通常只有一个或很少几个）")
    print("  2) 如仍有多个 head，用 `alembic revision --merge ...` 把它们合并为一个")
    print("  3) 确保 `3b_add_warehouses_and_locations.py` 的 down_revision 指向最终 head")
    print("  4) alembic upgrade head && pytest -q -m smoke")

if __name__ == "__main__":
    main()
