# app/services/snapshot_service.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

UTC = timezone.utc


class SnapshotService:
    """
    Snapshot / Inventory 服务（v2+v3）：

    1) 基于 stocks + batches + items 的实时 Inventory 查询：
       - query_inventory_snapshot
       - query_inventory_snapshot_paged

    2) Drawer V2 使用的单品明细接口：
       - query_item_detail

    3) v2/v3 快照合同（与 tests/services/test_snapshot_* 一致）：
       - run(session):
           * 尝试调用存储过程 snapshot_today();
           * 尝试读取视图 v_three_books;
           * 若上述对象不存在，则基于 stocks 重建 stock_snapshots，并返回汇总。
    """

    # ------------------------------------------------------------------
    # 0) v2/v3 快照入口：生成当日快照 + 返回汇总
    # ------------------------------------------------------------------
    @classmethod
    async def run(cls, session: AsyncSession) -> Dict[str, Any]:
        """
        兼容 snapshot_v2/v3 合同的入口：

        - 优先尝试调用存储过程 snapshot_today()（如存在）；
        - 尝试读取视图 v_three_books（如存在）；
        - 若上述对象不存在，则退回内建实现：
          * 以当前日期为 snapshot_date，将 stocks 汇总写入 stock_snapshots；
          * 返回一个总览字典 {sum_stocks, sum_ledger, sum_snapshot_on_hand, sum_snapshot_available}。
        """
        today = datetime.now(UTC).date()

        # 1) 尝试执行存储过程 snapshot_today()
        try:
            await session.execute(text("CALL snapshot_today()"))
        except Exception:
            # 如果 CALL 失败，当前事务可能已经处于 aborted 状态；
            # 需要先 rollback 一次，才能继续执行 DELETE/INSERT。
            try:
                await session.rollback()
            except Exception:
                # 如果当前 session 没有活动事务，忽略即可
                pass

            # 没有存储过程：手动重建当日快照
            await session.execute(
                text("DELETE FROM stock_snapshots WHERE snapshot_date = :d"),
                {"d": today},
            )
            await session.execute(
                text(
                    """
                    INSERT INTO stock_snapshots (
                        snapshot_date,
                        warehouse_id,
                        item_id,
                        batch_code,
                        qty_on_hand,
                        qty_available,
                        qty_allocated
                    )
                    SELECT
                        :d AS snapshot_date,
                        s.warehouse_id,
                        s.item_id,
                        s.batch_code,
                        SUM(s.qty) AS qty_on_hand,
                        SUM(s.qty) AS qty_available,
                        0 AS qty_allocated
                    FROM stocks AS s
                    GROUP BY s.warehouse_id, s.item_id, s.batch_code
                    """
                ),
                {"d": today},
            )

        # 2) 尝试读取 v_three_books 视图
        summary: Optional[Dict[str, Any]] = None
        try:
            res = await session.execute(text("SELECT * FROM v_three_books"))
            m = res.mappings().first()
            if m:
                summary = dict(m)
        except Exception:
            # 如果视图不存在或查询失败，同样要 rollback 一次，
            # 否则事务保持 aborted 状态，后续 _compute_summary 也会失败。
            try:
                await session.rollback()
            except Exception:
                pass
            summary = None

        # 3) 视图不存在时：手动汇总 stocks / stock_ledger / stock_snapshots
        if summary is None:
            summary = await cls._compute_summary(session)

        return summary

    @staticmethod
    async def _compute_summary(session: AsyncSession) -> Dict[str, Any]:
        """
        备用统计实现，用于在没有 v_three_books 视图时提供整体汇总。
        """
        row = await session.execute(
            text(
                """
                SELECT
                  COALESCE((SELECT SUM(qty) FROM stocks), 0)                    AS sum_stocks,
                  COALESCE((SELECT SUM(delta) FROM stock_ledger), 0)           AS sum_ledger,
                  COALESCE((SELECT SUM(qty_on_hand) FROM stock_snapshots), 0)  AS sum_snapshot_on_hand,
                  COALESCE((SELECT SUM(qty_available) FROM stock_snapshots),0) AS sum_snapshot_available
                """
            )
        )
        m = row.mappings().first() or {}
        return dict(m)

    # ------------------------------------------------------------------
    # 1) Inventory 实时查询（不依赖 snapshot 表）
    # ------------------------------------------------------------------
    @staticmethod
    async def query_inventory_snapshot(session: AsyncSession) -> List[Dict[str, Any]]:
        """
        返回扁平化的 inventory 列表，每行包含：
          - item_id
          - item_name
          - total_qty
          - top2_locations（字段名沿用旧结构，语义为“前两条明细”）
          - earliest_expiry（最早过期日）
          - near_expiry（在 30 天内即将过期）

        注意：batches 表已统一为 production_date / expiry_date，
        这里直接使用 expiry_date 字段作为过期日。
        """

        rows = (
            (
                await session.execute(
                    text(
                        """
                    SELECT
                        s.item_id,
                        i.name AS item_name,
                        s.warehouse_id,
                        s.batch_code,
                        s.qty,
                        b.expiry_date AS expiry_date
                    FROM stocks AS s
                    JOIN items AS i
                      ON i.id = s.item_id
                    LEFT JOIN batches AS b
                      ON b.item_id      = s.item_id
                     AND b.warehouse_id = s.warehouse_id
                     AND b.batch_code   = s.batch_code
                    WHERE s.qty <> 0
                    ORDER BY s.item_id, s.warehouse_id, s.batch_code
                    """
                    )
                )
            )
            .mappings()
            .all()
        )

        by_item: Dict[int, Dict[str, Any]] = {}
        today = datetime.now(UTC).date()
        near_delta = timedelta(days=30)

        for r in rows:
            item_id = int(r["item_id"])
            item_name = r["item_name"]
            wh_id = int(r["warehouse_id"])
            batch_code = r["batch_code"]
            qty = int(r["qty"] or 0)
            expiry_date = r.get("expiry_date")

            if item_id not in by_item:
                by_item[item_id] = {
                    "item_id": item_id,
                    "item_name": item_name,
                    "total_qty": 0,
                    "buckets": [],  # 临时存明细
                    "earliest_expiry": None,
                    "near_expiry": False,
                }

            rec = by_item[item_id]
            rec["total_qty"] += qty
            rec["buckets"].append(
                {
                    "warehouse_id": wh_id,
                    "batch_code": batch_code,
                    "qty": qty,
                    "expiry_date": expiry_date,
                }
            )

            if isinstance(expiry_date, date):
                # 最早过期日
                if rec["earliest_expiry"] is None or expiry_date < rec["earliest_expiry"]:
                    rec["earliest_expiry"] = expiry_date
                # 简单 near_expiry 判定：未来 30 天内到期
                if expiry_date >= today and (expiry_date - today) <= near_delta:
                    rec["near_expiry"] = True

        # 把 buckets 压成 top2_locations
        result: List[Dict[str, Any]] = []
        for _item_id, rec in by_item.items():
            buckets = sorted(rec["buckets"], key=lambda b: b["qty"], reverse=True)
            top2 = [
                {
                    "warehouse_id": b["warehouse_id"],
                    "batch_code": b["batch_code"],
                    "qty": b["qty"],
                }
                for b in buckets[:2]
            ]
            result.append(
                {
                    "item_id": rec["item_id"],
                    "item_name": rec["item_name"],
                    "total_qty": rec["total_qty"],
                    "top2_locations": top2,
                    "earliest_expiry": rec["earliest_expiry"],
                    "near_expiry": rec["near_expiry"],
                }
            )

        # 按 item_id 排序，保证输出稳定
        result.sort(key=lambda r: r["item_id"])
        return result

    @staticmethod
    async def query_inventory_snapshot_paged(
        session: AsyncSession,
        *,
        q: Optional[str] = None,
        offset: int = 0,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        基于 query_inventory_snapshot 的结果做内存分页 / 模糊搜索。

        - q：针对 item_name 做大小写不敏感匹配；
        - offset / limit：Python 层截断。
        """
        full = await SnapshotService.query_inventory_snapshot(session)

        if q:
            q_lower = q.lower()
            full = [r for r in full if q_lower in (r["item_name"] or "").lower()]

        total = len(full)
        rows = full[offset : offset + limit]

        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "rows": rows,
        }

    # ------------------------------------------------------------------
    # 2) Drawer V2 使用：单个商品的“仓 + 批次”明细
    # ------------------------------------------------------------------
    @staticmethod
    async def query_item_detail(
        session: AsyncSession,
        *,
        item_id: int,
        pools: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        返回单个商品的“仓 + 批次”明细。

        日期字段统一为 production_date / expiry_date：
        - 来自 batches.production_date / batches.expiry_date；
        - 与 FEFO / Count / Inbound / Batch Lifeline 使用同一套含义。
        """
        _pools = [p.upper() for p in (pools or [])] or ["MAIN"]  # 预留参数，不过滤

        rows = (
            (
                await session.execute(
                    text(
                        """
                    SELECT
                        s.item_id,
                        i.name AS item_name,
                        s.warehouse_id,
                        w.name AS warehouse_name,
                        s.batch_code,
                        s.qty,
                        b.production_date,
                        b.expiry_date
                    FROM stocks AS s
                    JOIN items AS i
                      ON i.id = s.item_id
                    JOIN warehouses AS w
                      ON w.id = s.warehouse_id
                    LEFT JOIN batches AS b
                      ON b.item_id      = s.item_id
                     AND b.warehouse_id = s.warehouse_id
                     AND b.batch_code   = s.batch_code
                    WHERE s.item_id = :item_id
                      AND s.qty <> 0
                    ORDER BY s.warehouse_id, s.batch_code
                    """
                    ),
                    {"item_id": item_id},
                )
            )
            .mappings()
            .all()
        )

        # 没有任何库存行时，返回“空明细”，避免前端直接 404
        if not rows:
            return {
                "item_id": item_id,
                "item_name": "",
                "totals": {
                    "on_hand_qty": 0,
                    "reserved_qty": 0,
                    "available_qty": 0,
                },
                "slices": [],
            }

        first = rows[0]
        item_name = first["item_name"]

        today = datetime.now(UTC).date()
        near_delta = timedelta(days=30)

        slices: List[Dict[str, Any]] = []
        total_on_hand = 0

        for r in rows:
            qty = int(r["qty"] or 0)
            if qty == 0:
                continue

            production_date = r.get("production_date")
            expiry_date = r.get("expiry_date")

            near = False
            if isinstance(expiry_date, date):
                if expiry_date >= today and (expiry_date - today) <= near_delta:
                    near = True

            pool = "MAIN"  # 目前统一视为 MAIN 池

            slice_rec: Dict[str, Any] = {
                "warehouse_id": int(r["warehouse_id"]),
                "warehouse_name": r["warehouse_name"],
                "pool": pool,
                "batch_code": r["batch_code"],
                "production_date": production_date,
                "expiry_date": expiry_date,
                "on_hand_qty": qty,
                "reserved_qty": 0,
                "available_qty": qty,
                "near_expiry": near,
                "is_top": False,  # 稍后再标记
            }
            slices.append(slice_rec)
            total_on_hand += qty

        # 根据 on_hand_qty 选出 Top2，标记 is_top
        if slices:
            ranked = sorted(
                list(enumerate(slices)),
                key=lambda kv: kv[1]["on_hand_qty"],
                reverse=True,
            )
            for idx, _rec in ranked[:2]:
                slices[idx]["is_top"] = True

        totals = {
            "on_hand_qty": total_on_hand,
            "reserved_qty": 0,
            "available_qty": total_on_hand,
        }

        return {
            "item_id": item_id,
            "item_name": item_name,
            "totals": totals,
            "slices": slices,
        }
