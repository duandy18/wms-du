# app/services/batch_service.py
from __future__ import annotations

from datetime import date
from typing import Iterable, Optional

from sqlalchemy import and_, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.batch import Batch


class BatchService:
    """
    v1.0 强契约 · 批次服务（同步 Session）

    对齐当前模型字段：
      - Batch(item_id, warehouse_id, location_id, batch_code, qty, production_date, expiry_date)

    提供：
      - ensure_batch(...)：按 (item_id, warehouse_id, location_id, batch_code) 确保批次存在
      - list_fefo(...)：按 FEFO（expiry_date 升序，NULL 最后，id 升序）列出批次
      - increment_qty(...)：带行级锁的安全增减（不可负）
      - set_qty(...)：直接设定 qty（不可负）
      - latest_expired(...)：查询某范围内“最新的一条过期批次”（按 id 最大）

    说明：
      - 本服务**不写台账**；台账统一由 Stock/Outbound 等服务负责。
      - 与 Putaway/Transfer 协同时，只负责批次数量层的原子性更新。
    """

    def __init__(self, db_session: Session) -> None:
        self.db: Session = db_session

    # ------------------------------------------------------------------
    # 基础：获取 / 创建
    # ------------------------------------------------------------------

    def ensure_batch(
        self,
        *,
        item_id: int,
        warehouse_id: int,
        location_id: int,
        batch_code: str,
        production_date: Optional[date] = None,
        expiry_date: Optional[date] = None,
    ) -> Batch:
        """
        确保 (item_id, warehouse_id, location_id, batch_code) 存在；如无则创建一条 qty=0 的记录。
        并返回 Batch 实体（持久态）。
        """
        q = (
            self.db.query(Batch)
            .filter(
                Batch.item_id == item_id,
                Batch.warehouse_id == warehouse_id,
                Batch.location_id == location_id,
                Batch.batch_code == batch_code,
            )
            .limit(1)
        )
        row: Optional[Batch] = q.first()
        if row:
            return row

        try:
            b = Batch(
                item_id=item_id,
                warehouse_id=warehouse_id,
                location_id=location_id,
                batch_code=batch_code,
                qty=0,
                production_date=production_date,
                expiry_date=expiry_date,
            )
            self.db.add(b)
            self.db.commit()
            self.db.refresh(b)
            return b
        except SQLAlchemyError:
            # 并发下可能已被其他事务创建；回滚后再查一次
            self.db.rollback()
            row2 = (
                self.db.query(Batch)
                .filter(
                    Batch.item_id == item_id,
                    Batch.warehouse_id == warehouse_id,
                    Batch.location_id == location_id,
                    Batch.batch_code == batch_code,
                )
                .first()
            )
            if row2 is None:
                raise
            return row2

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
        """
        按 FEFO 返回批次列表：expiry_date 升序（NULL 最后），id 升序。
        默认仅返回 qty>0 的批次；若 include_zero=True，则包含 qty=0。
        """
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
        """
        返回“最新的一条过期批次”（按 id 最大；qty>0），无则返回 None。
        """
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

        row = (
            self.db.query(Batch)
            .filter(and_(*conds))
            .order_by(Batch.id.desc())
            .first()
        )
        return row

    # ------------------------------------------------------------------
    # 写：数量调整（行级锁，非负）
    # ------------------------------------------------------------------

    def increment_qty(self, *, batch_id: int, delta: int) -> Batch:
        """
        增量调整批次数量；内部对该行加锁，保证并发安全；禁止调成负数。
        返回刷新后的 Batch。
        """
        try:
            with self.db.begin():
                b: Optional[Batch] = (
                    self.db.query(Batch)
                    .filter(Batch.id == batch_id)
                    .with_for_update()
                    .first()
                )
                if b is None:
                    raise ValueError(f"批次不存在：id={batch_id}")
                new_val = int(b.qty or 0) + int(delta)
                if new_val < 0:
                    raise ValueError("批次数量不能为负数")
                b.qty = new_val
            # 结束 with 会 commit
            self.db.refresh(b)  # type: ignore[arg-type]
            return b  # type: ignore[return-value]
        except Exception:
            self.db.rollback()
            raise

    def set_qty(self, *, batch_id: int, qty: int) -> Batch:
        """
        直接设定批次数量；内部对该行加锁；禁止设为负数。
        返回刷新后的 Batch。
        """
        if int(qty) < 0:
            raise ValueError("批次数量不能为负数")
        try:
            with self.db.begin():
                b: Optional[Batch] = (
                    self.db.query(Batch)
                    .filter(Batch.id == batch_id)
                    .with_for_update()
                    .first()
                )
                if b is None:
                    raise ValueError(f"批次不存在：id={batch_id}")
                b.qty = int(qty)
            self.db.refresh(b)  # type: ignore[arg-type]
            return b  # type: ignore[return-value]
        except Exception:
            self.db.rollback()
            raise

    # ------------------------------------------------------------------
    # 统计：按库位或仓汇总（可用于可视化/体检）
    # ------------------------------------------------------------------

    def summarize_by_location(
        self, *, item_id: int, location_id: int
    ) -> int:
        """
        返回某 item 在指定库位的批次数量总和（SUM(qty)）。
        """
        total = (
            self.db.query(func.coalesce(func.sum(Batch.qty), 0))
            .filter(Batch.item_id == item_id, Batch.location_id == location_id)
            .scalar()
        )
        return int(total or 0)

    def summarize_by_warehouse(
        self, *, item_id: int, warehouse_id: int
    ) -> int:
        """
        返回某 item 在指定仓的批次数量总和（SUM(qty)）。
        """
        total = (
            self.db.query(func.coalesce(func.sum(Batch.qty), 0))
            .filter(Batch.item_id == item_id, Batch.warehouse_id == warehouse_id)
            .scalar()
        )
        return int(total or 0)
