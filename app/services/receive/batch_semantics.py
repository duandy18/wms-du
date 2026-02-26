# app/services/receive/batch_semantics.py
from __future__ import annotations

from datetime import date
from typing import Literal, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

BatchMode = Literal["REQUIRED", "NONE"]

# Phase L：
# - “无批次”必须用 batch_code=None 表达（并由 lot_id 作为事实锚点），不鼓励/不接受 NULL_BATCH token 作为业务输入。
# - 仍然禁止 NOEXP/NONE 这种人为伪码作为批次。
_PSEUDO_BATCH_TOKENS = {
    "NOEXP",
    "NONE",
}


def batch_mode_from_has_shelf_life(has_shelf_life: bool) -> BatchMode:
    return "REQUIRED" if bool(has_shelf_life) else "NONE"


def normalize_batch_code(batch_code: Optional[str]) -> Optional[str]:
    if batch_code is None:
        return None
    s = str(batch_code).strip()
    return s or None


def is_pseudo_batch_code(batch_code: Optional[str]) -> bool:
    s = normalize_batch_code(batch_code)
    if s is None:
        return False
    return s.upper() in _PSEUDO_BATCH_TOKENS


def enforce_batch_semantics(
    *,
    batch_mode: BatchMode,
    production_date: Optional[date],
    expiry_date: Optional[date],
    batch_code: Optional[str],
) -> Tuple[Optional[date], Optional[date], Optional[str]]:
    """
    Phase 1A 批次两态封板（语义层）：

    - NONE：
        - batch_code 必须为 NULL
        - production_date / expiry_date 必须同时为 NULL

    - REQUIRED：
        - batch_code 必填，且禁止伪批次词（NOEXP/NONE）
        - production_date / expiry_date：允许为空；若填写则必须成对填写（避免半事实）
    """
    if batch_mode == "NONE":
        return None, None, None

    norm_code = normalize_batch_code(batch_code)
    if norm_code is None:
        raise ValueError("批次模式 REQUIRED：batch_code 必填")
    if is_pseudo_batch_code(norm_code):
        raise ValueError(f"批次模式 REQUIRED：禁止伪批次码 {norm_code!r}")

    # 日期允许为空；若填写则必须成对填写
    if (production_date is None) ^ (expiry_date is None):
        raise ValueError("批次模式 REQUIRED：production_date 与 expiry_date 必须同时提供或同时为空")

    return production_date, expiry_date, norm_code


async def ensure_batch_consistent(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    batch_code: str,
    production_date: Optional[date],
    expiry_date: Optional[date],
) -> None:
    """
    canonical（lots）一致性硬守护（Phase 4E 真收口）：

    - canonical 不存在：创建 SUPPLIER lot（以本次写入为准）
    - canonical 已存在：production/expiry 必须一致，否则 409

    注意：
    - 仅在 REQUIRED 且 production/expiry 都齐全时调用
    - 批次主档已统一迁移至 lots（lot-world）
    """
    code = str(batch_code).strip()
    if not code:
        raise ValueError("batch_code empty")

    row = await session.execute(
        text(
            """
            SELECT production_date, expiry_date
              FROM lots
             WHERE warehouse_id = :wid
               AND item_id      = :item_id
               AND lot_code_source = 'SUPPLIER'
               AND lot_code     = :code
             LIMIT 1
            """
        ),
        {"wid": int(warehouse_id), "item_id": int(item_id), "code": code},
    )
    existing = row.first()

    if existing is None:
        await session.execute(
            text(
                """
                INSERT INTO lots (
                    warehouse_id,
                    item_id,
                    lot_code_source,
                    lot_code,
                    production_date,
                    expiry_date,
                    expiry_source
                )
                VALUES (:wid, :item_id, 'SUPPLIER', :code, :pd, :ed, 'EXPLICIT')
                ON CONFLICT (warehouse_id, item_id, lot_code_source, lot_code)
                WHERE lot_code_source = 'SUPPLIER'
                DO UPDATE SET
                    production_date = lots.production_date,
                    expiry_date     = lots.expiry_date
                """
            ),
            {
                "wid": int(warehouse_id),
                "item_id": int(item_id),
                "code": code,
                "pd": production_date,
                "ed": expiry_date,
            },
        )
        return

    existing_pd = existing[0]
    existing_ed = existing[1]
    if existing_pd != production_date or existing_ed != expiry_date:
        raise HTTPException(
            status_code=409,
            detail=(
                "批次 canonical 不一致：lots 与本次写入的日期冲突。"
                f" (warehouse_id={int(warehouse_id)}, item_id={int(item_id)}, batch_code={code}, "
                f"canonical.production_date={existing_pd}, canonical.expiry_date={existing_ed}, "
                f"snapshot.production_date={production_date}, snapshot.expiry_date={expiry_date})"
            ),
        )
