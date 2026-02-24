# app/services/batch_service.py
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.api.batch_code_contract import normalize_optional_batch_code
from app.models.batch import Batch


class BatchService:
    """
    批次服务（同步 Session）

    ✅ 当前世界观（与 DB 对齐）：
    - 批次唯一维度：(item_id, warehouse_id, batch_code)
    - batches.batch_code NOT NULL（因此 norm_code=None 时，本服务不创建批次）
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
    ) -> Batch:
        norm_code = normalize_optional_batch_code(batch_code)
        if norm_code is None:
            raise ValueError("batches.batch_code is NOT NULL; batch_code must be provided for BatchService.ensure_batch")

        q = self.db.query(Batch).filter(
            Batch.item_id == item_id,
            Batch.warehouse_id == warehouse_id,
            Batch.batch_code == norm_code,
        )

        row: Optional[Batch] = q.limit(1).first()
        if row:
            return row

        b = Batch(
            item_id=item_id,
            warehouse_id=warehouse_id,
            batch_code=norm_code,
            production_date=production_date,
            expiry_date=expiry_date,
        )
        # qty 字段在很多环境已废弃/不存在，别硬写
        if hasattr(Batch, "qty"):
            setattr(b, "qty", 0)

        self.db.add(b)
        self.db.flush()
        self.db.refresh(b)
        return b

    def list_fefo(
        self,
        *,
        item_id: int,
        warehouse_id: Optional[int] = None,
        include_zero: bool = False,
    ) -> list[Batch]:
        conds = [Batch.item_id == item_id]
        if warehouse_id is not None:
            conds.append(Batch.warehouse_id == warehouse_id)

        q = self.db.query(Batch).filter(and_(*conds)).order_by(Batch.expiry_date.asc().nulls_last(), Batch.id.asc())
        # include_zero 仅在 Batch 有 qty 且你仍维护它时有意义
        if not include_zero and hasattr(Batch, "qty"):
            q = q.filter((Batch.qty.isnot(None)) & (Batch.qty > 0))

        return q.all()

    def latest_expired(
        self,
        *,
        item_id: int,
        on_day: Optional[date] = None,
        warehouse_id: Optional[int] = None,
    ) -> Optional[Batch]:
        today = on_day or date.today()
        conds = [
            Batch.item_id == item_id,
            Batch.expiry_date.isnot(None),
            Batch.expiry_date < today,
        ]
        if warehouse_id is not None:
            conds.append(Batch.warehouse_id == warehouse_id)

        q = self.db.query(Batch).filter(and_(*conds)).order_by(Batch.id.desc())

        if hasattr(Batch, "qty"):
            q = q.filter((Batch.qty.isnot(None)) & (Batch.qty > 0))

        return q.first()
