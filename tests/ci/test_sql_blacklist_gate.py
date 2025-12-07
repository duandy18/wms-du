"""
CI Gate: 禁止在受保护目录出现以下直 SQL 模式：
- INSERT INTO (stocks|stock_ledger|batches|stock_snapshots)
- UPDATE (stocks|stock_ledger|batches|stock_snapshots)
- SELECT ... FROM stocks

范围：
- 受保护目录：tests/services/**、tests/api/**、tests/contracts/**
- 允许直 SQL：tests/quick/**、tests/smoke/**、tests/db/**、tests/schema/**
- 临时豁免：列出当前尚未 helpers 化的具体文件（逐步清零后删除本豁免）
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# 受保护目录（业务/契约层）
PROTECTED_DIRS = ("tests/services", "tests/api", "tests/contracts")

# 明确允许直 SQL 的目录
ALLOW_DIRS = ("tests/quick", "tests/smoke", "tests/db", "tests/schema")

# —— 临时豁免文件（精确到文件路径；待 helpers 化后删除）——
TEMP_EXEMPT_FILES = {
    "tests/services/test_stock_on_hand_aggregation.py",
    "tests/services/test_fefo_allocator.py",
    "tests/services/test_db_views_and_proc.py",
    "tests/services/test_scan_putaway.py",
    "tests/services/test_scan_count.py",
    "tests/services/test_outbound_idem_audit_view.py",
    "tests/services/test_inventory_ops.py",
    "tests/services/test_scan_pick.py",
    "tests/services/test_batch_service.py",
    "tests/services/test_stock_auto_transfer_expired.py",
    "tests/services/test_fefo_rank_view_consistency.py",
    "tests/services/test_stock_service_contract.py",
    "tests/api/test_scan_gateway_putaway_commit.py",
    "tests/api/test_scan_gateway_count_commit.py",
    # ---- 下面是当前扫描出的尚未 helpers 化文件（Phase 3.7 临时豁免） ----
    "tests/services/test_outbound_service_adjust_path.py",
    "tests/services/test_platform_ship_soft_reserve.py",
    "tests/services/test_snapshot_reconcile_v3.py",
    "tests/services/test_fefo_soft_policy_v3.py",
    "tests/services/test_platform_outbound_flow_v3.py",
    "tests/services/test_order_outbound_flow_v3.py",
    "tests/services/test_order_reserve_anti_oversell.py",
    "tests/api/test_debug_trace_api.py",
    "tests/api/test_channel_inventory_api.py",
    "tests/services/soft_reserve/test_queue_restock_flow.py",
    "tests/services/soft_reserve/test_reservation_consumer_integration.py",
    "tests/services/soft_reserve/test_outbound_batch_merge_soft.py",
    "tests/services/soft_reserve/test_ship_replay_concurrency_soft.py",
    "tests/services/soft_reserve/test_ship_reserve_out_of_order_soft.py",
    "tests/services/phase34/test_adjust_stress_perf.py",
    "tests/services/phase34/test_ship_replay_concurrency.py",
    "tests/services/phase34/test_ship_reserve_out_of_order.py",
}

PATTERNS = [
    re.compile(r"INSERT\s+INTO\s+(stocks|stock_ledger|batches|stock_snapshots)\b", re.IGNORECASE),
    re.compile(r"UPDATE\s+(stocks|stock_ledger|batches|stock_snapshots)\b", re.IGNORECASE),
    re.compile(r"SELECT.+FROM\s+stocks\b", re.IGNORECASE | re.DOTALL),
]


def _norm(p: Path) -> str:
    return str(p).replace("\\", "/")


def _is_allowed(p: Path) -> bool:
    s = _norm(p)
    return any(s.startswith(prefix) for prefix in ALLOW_DIRS)


def _is_protected(p: Path) -> bool:
    s = _norm(p)
    return any(s.startswith(prefix) for prefix in PROTECTED_DIRS)


def _is_temp_exempt(p: Path) -> bool:
    return _norm(p) in TEMP_EXEMPT_FILES


@pytest.mark.asyncio
async def test_no_direct_sql_in_protected_dirs():
    repo_root = Path(".")
    offenders = []

    for p in repo_root.rglob("tests/**/*.py"):
        s = _norm(p)
        if not s.startswith("tests/"):
            continue
        if _is_allowed(p):
            continue
        if not _is_protected(p):
            continue
        if _is_temp_exempt(p):
            # 临时豁免文件：允许通过（后续逐步清零）
            continue

        try:
            txt = p.read_text(encoding="utf-8")
        except Exception:
            continue

        for pat in PATTERNS:
            for m in pat.finditer(txt):
                line_no = txt.count("\n", 0, m.start()) + 1
                snippet = txt[m.start() : m.end()].replace("\n", " ")
                offenders.append((s, line_no, snippet))

    if offenders:
        details = "\n".join(f"- {fn}:{ln} → {snip}" for fn, ln, snip in offenders)
        pytest.fail("直 SQL 黑名单命中（请改用 helpers 或服务接口）:\n" + details)
