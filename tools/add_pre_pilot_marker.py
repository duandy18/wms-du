#!/usr/bin/env python3
import re
from pathlib import Path

# 三颗黄金子弹的路径
TARGET_FILES = [
    Path("tests/phase2p9/test_fefo_outbound_three_books.py"),
    Path("tests/phase2p9/test_soft_reserve_trace_and_lifecycle_v2.py"),
    Path("tests/phase2p9/test_order_lifecycle_soft_reserve_and_ship.py"),
]

MARK = "@pytest.mark.pre_pilot"


def process_file(path: Path):
    if not path.exists():
        print(f"[WARN] File not found: {path}")
        return

    text = path.read_text()

    # 如果已经有标记，跳过
    if MARK in text:
        print(f"[SKIP] Marker already exists in {path}")
        return

    # 找测试函数定义（async def test_xxx）
    pattern = r"(@pytest\.mark\.asyncio\s*\n)?\s*async def test_"
    match = re.search(pattern, text)
    if not match:
        print(f"[WARN] No test function found in {path}")
        return

    # 在匹配处之前插入 pre_pilot 标记
    insert_pos = match.start()

    new_text = text[:insert_pos] + MARK + "\n" + text[insert_pos:]

    # 写回文件
    path.write_text(new_text)
    print(f"[OK] Added pre_pilot marker → {path}")


def main():
    for p in TARGET_FILES:
        process_file(p)


if __name__ == "__main__":
    main()
