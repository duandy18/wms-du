#!/usr/bin/env python3
"""
自动修复 Alembic 迁移图中的循环：
1) 扫描 app/db/migrations/versions/*.py
2) 解析: revision, down_revision(支持单值/tuple/带类型注解), Create Date/文件 mtime
3) 检测有向环；对每条环，按“创建时间早者为祖先”的规则，剪掉回边：
   - 让较新的 revision 的 down_revision 指向较旧者（或从其 down_revision 列表中移除较新者）
4) 每次改动都会写 .bak 备份
"""

import ast
import datetime
import glob
import os
import re
import shutil
import sys

VERS_DIR = "app/db/migrations/versions"

REV_RE = re.compile(r'^\s*revision\s*[:=]\s*[\'"]([^\'"]+)[\'"]\s*$', re.M)
DOWN_RE = re.compile(r"^\s*down_revision\s*[:=]\s*(.+)$", re.M)
DATE_RE = re.compile(r"Create Date:\s*([0-9]{4}-[0-9]{2}-[0-9]{2}\s+[0-9:]+)")


def parse_down_expr(expr: str) -> list[str]:
    """解析 down_revision 表达式，返回 revision 列表"""
    expr = expr.strip()
    # 去掉可能的类型标注前缀: Union[str,...] = ...
    if (
        expr.startswith("Union")
        or expr.startswith("(")
        or expr.startswith("[")
        or expr.startswith("{")
    ):
        pass
    try:
        # 尝试用 ast 解析右边表达式
        node = ast.parse(expr, mode="eval").body
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [node.value]
        elif isinstance(node, ast.Tuple) or isinstance(node, ast.List):
            vals = []
            for elt in node.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    vals.append(elt.value)
            return vals
        else:
            # 兜底：尝试简单正则抓字符串字面值
            return re.findall(r'["\']([^"\']+)["\']', expr)
    except Exception:
        return re.findall(r'["\']([^"\']+)["\']', expr)


def load_files() -> dict[str, dict]:
    out = {}
    for path in glob.glob(os.path.join(VERS_DIR, "*.py")):
        try:
            txt = open(path, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        m_rev = REV_RE.search(txt)
        if not m_rev:
            continue
        rev = m_rev.group(1).strip()
        m_down = DOWN_RE.search(txt)
        downs = parse_down_expr(m_down.group(1)) if m_down else []
        m_date = DATE_RE.search(txt)
        if m_date:
            try:
                create_dt = datetime.datetime.fromisoformat(m_date.group(1))
            except Exception:
                create_dt = None
        else:
            create_dt = None
        if not create_dt:
            try:
                create_dt = datetime.datetime.fromtimestamp(os.path.getmtime(path))
            except Exception:
                create_dt = datetime.datetime.min
        out[rev] = {
            "path": path,
            "downs": downs,  # list[str]
            "text": txt,
            "date": create_dt,
        }
    return out


def build_graph(meta: dict[str, dict]) -> dict[str, set[str]]:
    g = {rev: set(info["downs"]) for rev, info in meta.items()}
    # 只保留图中已知节点
    for rev, downs in g.items():
        g[rev] = {d for d in downs if d in meta}
    return g


def find_cycles(meta: dict[str, dict]) -> list[list[str]]:
    """简单 DFS 找环"""
    g = build_graph(meta)
    cycles = []
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {v: WHITE for v in g}
    stack: list[str] = []

    def dfs(u: str):
        color[u] = GRAY
        stack.append(u)
        for v in g[u]:
            if color.get(v, WHITE) == WHITE:
                dfs(v)
            elif color.get(v) == GRAY:
                # 找到环，截取
                if v in stack:
                    idx = stack.index(v)
                    cyc = stack[idx:].copy()
                    cycles.append(cyc)
        stack.pop()
        color[u] = BLACK

    for node in g:
        if color[node] == WHITE:
            dfs(node)
    # 去重（按集合）
    uniq = []
    seen = set()
    for cyc in cycles:
        key = tuple(sorted(cyc))
        if key not in seen:
            seen.add(key)
            uniq.append(cyc)
    return uniq


def rewrite_down(meta: dict[str, dict], rev: str, new_downs: list[str]) -> bool:
    info = meta[rev]
    txt = info["text"]
    # 用统一格式重写为 down_revision = <expr>
    # 还原为 tuple 或单值
    if len(new_downs) == 0:
        expr = "None"
    elif len(new_downs) == 1:
        expr = f'"{new_downs[0]}"'
    else:
        expr = "(" + ", ".join(f'"{d}"' for d in new_downs) + ")"
    new_txt = DOWN_RE.sub(f"down_revision = {expr}", txt, count=1)
    if new_txt != txt:
        bak = info["path"] + ".bak"
        shutil.copyfile(info["path"], bak)
        open(info["path"], "w", encoding="utf-8").write(new_txt)
        info["text"] = new_txt
        info["downs"] = new_downs
        return True
    return False


def fix_cycles(meta: dict[str, dict]) -> list[tuple[list[str], list[tuple[str, list[str]]]]]:
    """按创建时间规则剪环；返回 [(cycle_nodes, [(rev, new_downs), ...])...]"""
    changes = []
    while True:
        cycles = find_cycles(meta)
        if not cycles:
            break
        for cyc in cycles:
            # 选出此环中最“老”的节点作为祖先
            oldest = min(cyc, key=lambda r: meta[r]["date"])
            # 让其余节点的 down_revision 列表，移除指向“更新”的边（保留最老为祖先）
            patch_list = []
            for r in cyc:
                downs = meta[r]["downs"]
                # 去除任何指向比自己新的节点；保留指向更老或等老的
                new_downs = [
                    d for d in downs if meta.get(d) and (meta[d]["date"] <= meta[r]["date"])
                ]
                # 确保至少有一路能通向最老
                if r != oldest and oldest not in new_downs:
                    new_downs = (
                        [oldest] if not new_downs else list(dict.fromkeys(new_downs + [oldest]))
                    )
                if new_downs != downs:
                    if rewrite_down(meta, r, new_downs):
                        patch_list.append((r, new_downs))
            if patch_list:
                changes.append((cyc, patch_list))
        # 再次循环直到没有环
    return changes


def main():
    if not os.path.isdir(VERS_DIR):
        print(f"❌ not found: {VERS_DIR}")
        sys.exit(2)
    meta = load_files()
    if not meta:
        print("❌ no migration files found")
        sys.exit(2)
    changes = fix_cycles(meta)
    if not changes:
        print("ℹ️  no cycles detected or already fixed.")
    else:
        print("✅ cycles fixed:")
        for cyc, patches in changes:
            print(" - cycle:", " -> ".join(cyc))
            for r, new_downs in patches:
                print(
                    f"   * patched {r}: down_revision = {tuple(new_downs) if len(new_downs)>1 else (new_downs[0] if new_downs else None)}"
                )
    print("\nNext:")
    print("  1) alembic heads -v")
    print('  2) alembic revision --merge -m "merge heads" <HEAD_A> <HEAD_B>')
    print("  3) 更新“仓/库位”迁移的 down_revision 指向第2步生成的 merge 修订号")
    print("  4) alembic upgrade head && pytest -q -m smoke")


if __name__ == "__main__":
    main()
