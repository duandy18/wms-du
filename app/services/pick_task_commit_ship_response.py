# app/services/pick_task_commit_ship_response.py
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict


def build_ok_payload(
    *,
    idempotent: bool,
    task_id: int,
    warehouse_id: int,
    platform: str,
    shop_id: str,
    ref: str,
    trace_id: str,
    committed_at: str,
    diff_summary: Any,
    has_temp_lines: bool,
    temp_lines_n: int,
) -> Dict[str, Any]:
    """
    统一响应结构（对齐蓝皮书测试与既有 API 口径）

    committed_at:
      - ISO8601 字符串（UTC），用于 cockpit 展示/排序/可观测闭环
      - 幂等短路：优先使用 outbound_commits_v2.created_at（或回退 now）
      - 主路径：使用本次提交完成时刻（或回读 DB created_at）

    temp lines:
      - 临时事实行（order_id=None / note=TEMP_FACT）用于未来异常流程的护栏
      - 前端可直接提示“存在非订单行事实”
    """
    return {
        "status": "OK",
        "idempotent": bool(idempotent),
        "task_id": int(task_id),
        "warehouse_id": int(warehouse_id),
        "platform": str(platform),
        "shop_id": str(shop_id),
        "ref": str(ref),
        "trace_id": str(trace_id),
        "committed_at": str(committed_at),
        "diff": {
            "task_id": int(diff_summary.task_id),
            "has_over": bool(diff_summary.has_over),
            "has_under": bool(diff_summary.has_under),
            "has_temp_lines": bool(has_temp_lines),
            "temp_lines_n": int(temp_lines_n),
            "lines": [asdict(x) for x in diff_summary.lines],
        },
    }
