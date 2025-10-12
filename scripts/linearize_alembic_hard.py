#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全仓扫描 **/versions/*.py，按指定拓扑线性化 down_revision，剪掉 Alembic 环。
为每个改动文件生成 .bak 备份；仅改 `down_revision` 一行，DDL 不动。
"""
import os, re, io, glob, shutil, ast, sys
from typing import Dict, List, Optional

# 需要线性化的 7 个 revision（子 -> 父）
WANT = {
    "2a01baddb001": "31fc28eac057",
    "2a01baddb002": "2a01baddb001",
    "3a_fix_sqlite_inline_pks": "2a01baddb002",
    "1088800f816e": "3a_fix_sqlite_inline_pks",
    "1f9e5c2b8a11": "1088800f816e",
    "1223487447f9": "1f9e5c2b8a11",
    "bdc33e80391a": "1223487447f9",
}

REV_RE  = re.compile(r'^\s*revision\s*[:=]\s*[\'"]([^\'"]+)[\'"]\s*$', re.M)
DOWN_RE = re.compile(r'^\s*down_revision\s*[:=]\s*(.+)$', re.M)

def parse_down_expr(expr: str) -> List[str]:
    expr = expr.strip()
    try:
        node = ast.parse(expr, mode="eval").body
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [node.value]
        if isinstance(node, (ast.Tuple, ast.List)):
            out=[]
            for e in node.elts:
                if isinstance(e, ast.Constant) and isinstance(e.value, str):
                    out.append(e.value)
            return out
    except Exception:
        pass
    return re.findall(r'["\']([^"\']+)["\']', expr)

def find_version_files() -> List[str]:
    files = []
    for pat in ("**/versions/*.py",):
        files.extend(glob.glob(pat, recursive=True))
    return sorted(set(files))

def read(path: str) -> Optional[str]:
    try:
        return io.open(path, "r", encoding="utf-8", errors="ignore").read()
    except Exception:
        return None

def write_with_backup(path: str, text: str):
    shutil.copyfile(path, path + ".bak")
    io.open(path, "w", encoding="utf-8").write(text)

def main():
    files = find_version_files()
    if not files:
        print("❌ 未找到任何迁移文件（**/versions/*.py）"); sys.exit(2)

    rev2file: Dict[str, str] = {}
    file2text: Dict[str, str] = {}
    for p in files:
        txt = read(p)
        if txt is None: continue
        m = REV_RE.search(txt)
        if not m: continue
        rev = m.group(1).strip()
        rev2file[rev] = p
        file2text[p] = txt

    changed = []
    missing = []
    for child, parent in WANT.items():
        p = rev2file.get(child)
        if not p:
            missing.append(child); continue
        txt = file2text[p]
        if not DOWN_RE.search(txt):
            # 如果没有 down_revision 行，直接追加一行
            new_txt = txt + f'\n\ndown_revision = "{parent}"\n'
        else:
            new_txt = DOWN_RE.sub(f'down_revision = "{parent}"', txt, count=1)
        if new_txt != txt:
            write_with_backup(p, new_txt)
            file2text[p] = new_txt
            changed.append((child, parent, p))

    if changed:
        print("✅ 已线性化以下迁移（已生成 .bak 备份）：")
        for c,pth,fp in changed:
            print(f" - {c} -> {pth}   ({fp})")
    else:
        print("ℹ️ 没有改动（可能已经线性化）")

    if missing:
        print("⚠️ 未在文件中找到这些 revision（需你手工核对）：", ", ".join(missing))

    print("\n下一步：")
    print("  1) alembic heads -v")
    print("  2) 若仍有多个 head：alembic revision --merge -m \"merge heads\" <HEAD_A> <HEAD_B>")
    print("  3) 确保 warehouses/locations 迁移的 down_revision 指向唯一 head 或 merge 修订")
    print("  4) alembic upgrade head && pytest -q -m smoke")

if __name__ == "__main__":
    main()
