# app/services/receive_task_commit_parts/validations.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.models.receive_task import ReceiveTask


def validate_task_before_commit(task: ReceiveTask) -> None:
    if task.status != "DRAFT":
        raise ValueError(f"任务 {task.id} 状态为 {task.status}，不能重复 commit")
    if not task.lines:
        raise ValueError(f"任务 {task.id} 没有任何行，不能 commit")


def validate_lines_shelf_life(task: ReceiveTask, policy_map: dict[int, dict[str, object]]) -> None:
    # commit 前校验：以 has_shelf_life 为准
    for line in task.lines or []:
        if not line.scanned_qty or line.scanned_qty == 0:
            continue

        info = policy_map.get(int(line.item_id)) or {}
        has_sl = bool(info.get("has_shelf_life") or False)
        item_name = info.get("name") or line.item_name or f"item_id={line.item_id}"

        # ✅ 非批次商品（has_sl=false）：无 batch_code 直接保持 None（主线：无批次槽位）
        # ✅ 批次商品（has_sl=true）：batch_code 必须存在
        if not line.batch_code or not str(line.batch_code).strip():
            if has_sl:
                raise ValueError(f"{item_name} 需要有效期管理，批次不能为空")
            line.batch_code = None

        if has_sl:
            if line.production_date is None:
                raise ValueError(f"{item_name} 需要有效期管理，必须填写生产日期")
            if line.expiry_date is None:
                sv = info.get("shelf_life_value")
                su = info.get("shelf_life_unit")
                if sv is None or su is None or not str(su).strip():
                    raise ValueError(
                        f"{item_name} 未填写到期日期，且商品未配置保质期参数，无法推算到期日期"
                    )


def choose_now(occurred_at: Optional[datetime], utc) -> datetime:
    return occurred_at or datetime.now(utc)
