# app/services/receive_task_commit_validate.py
from __future__ import annotations

from typing import Any, Dict

from app.services.receive_task_commit_constants import NOEXP_BATCH_CODE


def validate_and_prepare_lines(task, policy_map: Dict[int, Dict[str, Any]]) -> None:
    """
    commit 前校验：以 has_shelf_life 为准（与原逻辑保持一致）

    - 对 scanned_qty == 0 的行：跳过（不要求批次/日期）
    - 对 has_shelf_life = true：
        * batch_code 必须
        * production_date 必须
        * expiry_date 可缺省，但缺省时必须有 shelf_life_value/unit（用于推算）
    - 对 has_shelf_life = false：
        * batch_code 为空则自动 NOEXP
        * 不要求 production/expiry
    """
    for line in task.lines:
        if not line.scanned_qty or line.scanned_qty == 0:
            continue

        info = policy_map.get(int(line.item_id)) or {}
        has_sl = bool(info.get("has_shelf_life") or False)
        item_name = info.get("name") or line.item_name or f"item_id={line.item_id}"

        # batch_code：两种都要求（无有效期可自动 NOEXP）
        if not line.batch_code or not str(line.batch_code).strip():
            if has_sl:
                raise ValueError(f"{item_name} 需要有效期管理，批次不能为空")
            line.batch_code = NOEXP_BATCH_CODE

        if has_sl:
            # 必须生产日期
            if line.production_date is None:
                raise ValueError(f"{item_name} 需要有效期管理，必须填写生产日期")
            # expiry 可缺省，但缺省时必须有参数可推算
            if line.expiry_date is None:
                sv = info.get("shelf_life_value")
                su = info.get("shelf_life_unit")
                if sv is None or su is None or not str(su).strip():
                    raise ValueError(
                        f"{item_name} 未填写到期日期，且商品未配置保质期参数，无法推算到期日期"
                    )
        else:
            # 无有效期管理：不要求日期
            pass
