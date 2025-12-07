#!/usr/bin/env python3
from pathlib import Path

# 这 4 个是你 pytest -m pre_pilot 输出里被 skip 的 legacy 文件
LEGACY_FILES = [
    Path("tests/sandbox/test_routing_sandbox_full_chain.py"),
    Path("tests/services/test_outbound_v2_basic.py"),
    Path("tests/services/test_outbound_v2_fefo_soft.py"),
    Path("tests/smoke/test_smoke_main_v2.py"),
]

OLD = "pytest.mark.pre_pilot"
NEW = "pytest.mark.grp_legacy"  # 你也可以改成 grp_events 等


def process_file(path: Path):
    if not path.exists():
        print(f"[WARN] file not found: {path}")
        return

    content = path.read_text()

    if OLD not in content:
        print(f"[SKIP] no '{OLD}' found in {path}")
        return

    new_content = content.replace(OLD, NEW)
    path.write_text(new_content)

    print(f"[OK] replaced '{OLD}' -> '{NEW}' in {path}")


def main():
    for p in LEGACY_FILES:
        process_file(p)


if __name__ == "__main__":
    main()
