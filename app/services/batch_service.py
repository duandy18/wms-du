# app/services/batch_service.py
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.api.batch_code_contract import normalize_optional_batch_code
from app.models.batch import Batch


class BatchService:
    """
    v1.0 强契约 · 批次服务（同步 Session）

    约定：
    - 不在服务内 commit/rollback；事务由调用方控制。
    - 本服务**不写台账**；仅维护批次行本身。

    ✅ 主线 B：批次语义与 NULL 世界观对齐
    - batch_code 允许为 NULL（用于无批次槽位对齐/兼容）
    - 查询/创建时必须正确处理 NULL（避免 NULL= NULL 吞数据）
    """

    def __init__(self, db_session: Session) -> None:
        self.db: Session = db_session

    # ------------------------------------------------------------------
    # 基础：获取 / 创建（无显式 commit；调用方负责事务）
    # ------------------------------------------------------------------
    def ensure_batch(
        self,
        *,
        item_id: int,
        warehouse_id: int,
        location_id: int,
        batch_code: Optional[str] = None,
        production_date: Optional[date] = None,
        expiry_date: Optional[date] = None,
    ) -> Batch:
        norm_code = normalize_optional_batch_code(batch_code)

        q = self.db.query(Batch).filter(
            Batch.item_id == item_id,
            Batch.warehouse_id == warehouse_id,
            Batch.location_id == location_id,
        )

        # ✅ NULL 语义：必须用 IS NULL，而不是 ==（避免 NULL= NULL 的歧义）
        if norm_code is None:
            q = q.filter(Batch.batch_code.is_(None))
        else:
            q = q.filter(Batch.batch_code == norm_code)

        row: Optional[Batch] = q.limit(1).first()
        if row:
            return row

        b = Batch(
            item_id=item_id,
            warehouse_id=warehouse_id,
            location_id=location_id,
            batch_code=norm_code,
            qty=0,
            production_date=production_date,
            expiry_date=expiry_date,
        )
        self.db.add(b)
        self.db.flush()  # 让 b 获得 id
        self.db.refresh(b)
        return b

    # ------------------------------------------------------------------
    # 查询：FEFO / 过滤
    # ------------------------------------------------------------------
    def list_fefo(
        self,
        *,
        item_id: int,
        warehouse_id: Optional[int] = None,
        location_id: Optional[int] = None,
        include_zero: bool = False,
    ) -> list[Batch]:
        conds = [Batch.item_id == item_id]
        if warehouse_id is not None:
            conds.append(Batch.warehouse_id == warehouse_id)
        if location_id is not None:
            conds.append(Batch.location_id == location_id)
        if not include_zero:
            conds.append((Batch.qty.isnot(None)) & (Batch.qty > 0))

        rows = (
            self.db.query(Batch)
            .filter(and_(*conds))
            .order_by(Batch.expiry_date.asc().nulls_last(), Batch.id.asc())
            .all()
        )
        return rows

    def latest_expired(
        self,
        *,
        item_id: int,
        on_day: Optional[date] = None,
        warehouse_id: Optional[int] = None,
        location_id: Optional[int] = None,
    ) -> Optional[Batch]:
        today = on_day or date.today()
        conds = [
            Batch.item_id == item_id,
            (Batch.qty.isnot(None)) & (Batch.qty > 0),
            Batch.expiry_date.isnot(None),
            Batch.expiry_date < today,
        ]
        if warehouse_id is not None:
            conds.append(Batch.warehouse_id == warehouse_id)
        if location_id is not None:
            conds.append(Batch.location_id == location_id)

        row = self.db.query(Batch).filter(and_(*conds)).order_by(Batch.id.desc()).first()
        return row

    # ------------------------------------------------------------------
    # 写：数量调整（行级锁，非负；无显式 commit）
    # ------------------------------------------------------------------
    def increment_qty(self, *, batch_id: int, delta: int) -> Batch:
        b: Optional[Batch] = self.db.query(Batch).filter(Batch.id == batch_id).with_for_update().first()
        if b is None:
            raise ValueError(f"批次不存在：id={batch_id}")
        new_val = int(b.qty or 0) + int(delta)
        if new_val < 0:
            raise ValueError("批次数量不能为负数")
        b.qty = new_val
        self.db.flush()
        self.db.refresh(b)
        return b  # type: ignore[return-value]

    def set_qty(self, *, batch_id: int, qty: int) -> Batch:
        if int(qty) < 0:
            raise ValueError("批次数量不能为负数")
        b: Optional[Batch] = self.db.query(Batch).filter(Batch.id == batch_id).with_for_update().first()
        if b is None:
            raise ValueError(f"批次不存在：id={batch_id}")
        b.qty = int(qty)
        self.db.flush()
        self.db.refresh(b)
        return b  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # 统计：按库位或仓汇总（可用于可视化/体检）
    # ------------------------------------------------------------------
    def summarize_by_location(self, *, item_id: int, location_id: int) -> int:
        total = (
            self.db.query(func.coalesce(func.sum(Batch.qty), 0))
            .filter(Batch.item_id == item_id, Batch.location_id == location_id)
            .scalar()
        )
        return int(total or 0)

    def summarize_by_warehouse(self, *, item_id: int, warehouse_id: int) -> int:
        total = (
            self.db.query(func.coalesce(func.sum(Batch.qty), 0))
            .filter(Batch.item_id == item_id, Batch.warehouse_id == warehouse_id)
            .scalar()
        )
        return int(total or 0)
