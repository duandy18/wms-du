# app/services/batch_service.py
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session


class BatchService:
    """
    批次服务（同步 Session）

    Phase 4E（真收口）：
    - 禁止读取/写入 legacy 批次表
    - 批次 canonical 已迁移到 lots（AsyncSession 路径）
    - 同步 Session 下的 BatchService 作为 legacy API，必须禁用以避免暗中回退
    """

    def __init__(self, db_session: Session) -> None:
        self.db: Session = db_session

    def ensure_batch(
        self,
        *,
        item_id: int,
        warehouse_id: int,
        batch_code: Optional[str] = None,
        production_date: Optional[date] = None,
        expiry_date: Optional[date] = None,
    ):
        _ = item_id
        _ = warehouse_id
        _ = batch_code
        _ = production_date
        _ = expiry_date
        raise RuntimeError(
            "Phase 4E: BatchService(legacy batch API) 已禁用。"
            "请改用 lots（lot-world）路径：在 AsyncSession 执行链路中 ensure SUPPLIER lot，并使用 stocks_lot 作为余额源。"
        )

    def list_fefo(
        self,
        *,
        item_id: int,
        warehouse_id: Optional[int] = None,
        include_zero: bool = False,
    ):
        _ = item_id
        _ = warehouse_id
        _ = include_zero
        raise RuntimeError(
            "Phase 4E: BatchService.list_fefo(legacy batch API) 已禁用。"
            "请改用 lots + stocks_lot（expiry_date ASC + qty>0）。"
        )

    def latest_expired(
        self,
        *,
        item_id: int,
        on_day: Optional[date] = None,
        warehouse_id: Optional[int] = None,
    ):
        _ = item_id
        _ = on_day
        _ = warehouse_id
        raise RuntimeError(
            "Phase 4E: BatchService.latest_expired(legacy batch API) 已禁用。"
            "请改用 lots（expiry_date）+ stocks_lot（qty>0）。"
        )
