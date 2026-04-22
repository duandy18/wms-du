from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.wms.inventory_adjustment.count.models.count_doc import (
    CountDoc,
    CountDocLine,
)


class CountDocRepo:
    async def create_doc(
        self,
        session: AsyncSession,
        *,
        count_no: str,
        warehouse_id: int,
        snapshot_at: datetime,
        created_by: int | None,
        remark: str | None,
    ) -> CountDoc:
        obj = CountDoc(
            count_no=str(count_no),
            warehouse_id=int(warehouse_id),
            snapshot_at=snapshot_at,
            created_by=int(created_by) if created_by is not None else None,
            remark=remark,
            status="DRAFT",
        )
        session.add(obj)
        await session.flush()
        return obj

    async def get_doc(
        self,
        session: AsyncSession,
        *,
        doc_id: int,
    ) -> CountDoc | None:
        stmt = select(CountDoc).where(CountDoc.id == int(doc_id))
        return (await session.execute(stmt)).scalar_one_or_none()

    async def get_doc_detail(
        self,
        session: AsyncSession,
        *,
        doc_id: int,
    ) -> CountDoc | None:
        stmt = (
            select(CountDoc)
            .where(CountDoc.id == int(doc_id))
            .options(
                selectinload(CountDoc.lines).selectinload(CountDocLine.lot_snapshots),
            )
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def list_docs(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[int, list[CountDoc]]:
        where_sql = ""
        params: dict[str, object] = {
            "limit": int(limit),
            "offset": int(offset),
        }
        if warehouse_id is not None:
            where_sql = "WHERE warehouse_id = :warehouse_id"
            params["warehouse_id"] = int(warehouse_id)

        total_sql = text(
            f"""
            SELECT COUNT(*)
              FROM count_docs
              {where_sql}
            """
        )
        total = int((await session.execute(total_sql, params)).scalar_one() or 0)

        stmt = (
            select(CountDoc)
            .order_by(CountDoc.snapshot_at.desc(), CountDoc.id.desc())
            .limit(int(limit))
            .offset(int(offset))
        )
        if warehouse_id is not None:
            stmt = stmt.where(CountDoc.warehouse_id == int(warehouse_id))

        items = list((await session.execute(stmt)).scalars().all())
        return total, items

    async def freeze_doc_lines_from_current_stock(
        self,
        session: AsyncSession,
        *,
        doc_id: int,
    ) -> tuple[int, int]:
        """
        当前一版盘点采用“盘点时冻结该仓库存动作”的方案，因此：
        - snapshot_at 即冻结时点；
        - 冻结明细直接从当前 stocks_lot 聚合；
        - 主行按 item 粒度生成；
        - lot 分布下沉到 count_doc_line_lot_snapshots。
        """
        doc = await self.get_doc(session, doc_id=int(doc_id))
        if doc is None:
            raise LookupError(f"count_doc_not_found:{int(doc_id)}")

        # 先清旧冻结结果（当前阶段允许在 DRAFT 下重冻）
        await session.execute(
            text(
                """
                DELETE FROM count_doc_line_lot_snapshots
                 WHERE line_id IN (
                    SELECT id
                      FROM count_doc_lines
                     WHERE doc_id = :doc_id
                 )
                """
            ),
            {"doc_id": int(doc_id)},
        )
        await session.execute(
            text("DELETE FROM count_doc_lines WHERE doc_id = :doc_id"),
            {"doc_id": int(doc_id)},
        )

        # 1) 生成商品级盘点主行
        await session.execute(
            text(
                """
                INSERT INTO count_doc_lines (
                  doc_id,
                  line_no,
                  item_id,
                  item_name_snapshot,
                  item_spec_snapshot,
                  snapshot_qty_base
                )
                SELECT
                  :doc_id AS doc_id,
                  ROW_NUMBER() OVER (ORDER BY s.item_id ASC) AS line_no,
                  s.item_id,
                  MAX(i.name) AS item_name_snapshot,
                  MAX(i.spec) AS item_spec_snapshot,
                  SUM(s.qty) AS snapshot_qty_base
                  FROM stocks_lot s
                  JOIN items i
                    ON i.id = s.item_id
                 WHERE s.warehouse_id = :warehouse_id
                 GROUP BY s.item_id
                HAVING SUM(s.qty) > 0
                """
            ),
            {
                "doc_id": int(doc_id),
                "warehouse_id": int(doc.warehouse_id),
            },
        )

        # 2) 生成该商品行下的 lot 快照参考
        await session.execute(
            text(
                """
                INSERT INTO count_doc_line_lot_snapshots (
                  line_id,
                  lot_id,
                  lot_code_snapshot,
                  snapshot_qty_base
                )
                SELECT
                  l.id AS line_id,
                  sl.lot_id,
                  MAX(lo.lot_code) AS lot_code_snapshot,
                  SUM(sl.qty) AS snapshot_qty_base
                  FROM count_doc_lines l
                  JOIN count_docs d
                    ON d.id = l.doc_id
                  JOIN stocks_lot sl
                    ON sl.item_id = l.item_id
                   AND sl.warehouse_id = d.warehouse_id
                  JOIN lots lo
                    ON lo.id = sl.lot_id
                 WHERE l.doc_id = :doc_id
                 GROUP BY l.id, sl.lot_id
                HAVING SUM(sl.qty) > 0
                """
            ),
            {"doc_id": int(doc_id)},
        )

        await session.execute(
            text(
                """
                UPDATE count_docs
                   SET status = 'FROZEN'
                 WHERE id = :doc_id
                """
            ),
            {"doc_id": int(doc_id)},
        )

        line_count = int(
            (
                await session.execute(
                    text("SELECT COUNT(*) FROM count_doc_lines WHERE doc_id = :doc_id"),
                    {"doc_id": int(doc_id)},
                )
            ).scalar_one()
            or 0
        )

        lot_snapshot_count = int(
            (
                await session.execute(
                    text(
                        """
                        SELECT COUNT(*)
                          FROM count_doc_line_lot_snapshots
                         WHERE line_id IN (
                            SELECT id
                              FROM count_doc_lines
                             WHERE doc_id = :doc_id
                         )
                        """
                    ),
                    {"doc_id": int(doc_id)},
                )
            ).scalar_one()
            or 0
        )

        return line_count, lot_snapshot_count

    async def update_line_counts(
        self,
        session: AsyncSession,
        *,
        doc_id: int,
        lines: Sequence[dict[str, object]],
    ) -> int:
        """
        入参 lines 约定每项至少包含：
        - line_id
        - counted_item_uom_id
        - counted_qty_input
        可选：
        - reason_code
        - disposition
        - remark
        """
        updated = 0

        for raw in lines:
            line_id = int(raw["line_id"])
            counted_item_uom_id = int(raw["counted_item_uom_id"])
            counted_qty_input = int(raw["counted_qty_input"])

            line = (
                await session.execute(
                    select(CountDocLine).where(
                        CountDocLine.id == line_id,
                        CountDocLine.doc_id == int(doc_id),
                    )
                )
            ).scalar_one_or_none()
            if line is None:
                raise LookupError(f"count_doc_line_not_found:{line_id}")

            uom_row = (
                await session.execute(
                    text(
                        """
                        SELECT
                          iu.id,
                          iu.ratio_to_base,
                          COALESCE(NULLIF(iu.display_name, ''), iu.uom) AS uom_name_snapshot
                          FROM item_uoms iu
                         WHERE iu.id = :uom_id
                           AND iu.item_id = :item_id
                         LIMIT 1
                        """
                    ),
                    {
                        "uom_id": int(counted_item_uom_id),
                        "item_id": int(line.item_id),
                    },
                )
            ).mappings().first()
            if uom_row is None:
                raise LookupError(
                    f"count_doc_line_invalid_item_uom_pair: line_id={line_id}, item_uom_id={counted_item_uom_id}"
                )

            ratio = int(uom_row["ratio_to_base"])
            uom_name_snapshot = str(uom_row["uom_name_snapshot"])
            counted_qty_base = int(counted_qty_input) * int(ratio)
            diff_qty_base = int(counted_qty_base) - int(line.snapshot_qty_base)

            line.counted_item_uom_id = int(counted_item_uom_id)
            line.counted_uom_name_snapshot = uom_name_snapshot
            line.counted_ratio_to_base_snapshot = int(ratio)
            line.counted_qty_input = int(counted_qty_input)
            line.counted_qty_base = int(counted_qty_base)
            line.diff_qty_base = int(diff_qty_base)

            reason_code = raw.get("reason_code")
            disposition = raw.get("disposition")
            remark = raw.get("remark")

            line.reason_code = str(reason_code).strip() if isinstance(reason_code, str) and reason_code.strip() else None
            line.disposition = (
                str(disposition).strip() if isinstance(disposition, str) and disposition.strip() else None
            )
            line.remark = str(remark).strip() if isinstance(remark, str) and remark.strip() else None
            line.updated_at = datetime.now(timezone.utc)

            updated += 1

        await session.flush()
        return updated

    async def try_mark_doc_counted(
        self,
        session: AsyncSession,
        *,
        doc_id: int,
    ) -> bool:
        """
        当且仅当：
        - 当前为 FROZEN
        - 至少存在一条明细
        - 所有明细都已有 counted_qty_base
        才推进到 COUNTED。
        """
        result = await session.execute(
            text(
                """
                UPDATE count_docs
                   SET status = 'COUNTED',
                       counted_at = COALESCE(counted_at, now())
                 WHERE id = :doc_id
                   AND status = 'FROZEN'
                   AND EXISTS (
                       SELECT 1
                         FROM count_doc_lines
                        WHERE doc_id = :doc_id
                   )
                   AND NOT EXISTS (
                       SELECT 1
                         FROM count_doc_lines
                        WHERE doc_id = :doc_id
                          AND counted_qty_base IS NULL
                   )
                """
            ),
            {"doc_id": int(doc_id)},
        )
        return bool(result.rowcount and int(result.rowcount) > 0)

    async def mark_doc_posted(
        self,
        session: AsyncSession,
        *,
        doc_id: int,
        posted_event_id: int,
        posted_at: datetime,
    ) -> None:
        result = await session.execute(
            text(
                """
                UPDATE count_docs
                   SET status = 'POSTED',
                       posted_event_id = :posted_event_id,
                       posted_at = :posted_at
                 WHERE id = :doc_id
                   AND status = 'COUNTED'
                """
            ),
            {
                "doc_id": int(doc_id),
                "posted_event_id": int(posted_event_id),
                "posted_at": posted_at,
            },
        )
        if not result.rowcount:
            raise LookupError(f"count_doc_not_counted_or_not_found:{int(doc_id)}")

    async def mark_doc_voided(
        self,
        session: AsyncSession,
        *,
        doc_id: int,
    ) -> None:
        result = await session.execute(
            text(
                """
                UPDATE count_docs
                   SET status = 'VOIDED'
                 WHERE id = :doc_id
                   AND status IN ('DRAFT', 'FROZEN', 'COUNTED')
                """
            ),
            {"doc_id": int(doc_id)},
        )
        if not result.rowcount:
            raise LookupError(f"count_doc_not_voidable_or_not_found:{int(doc_id)}")


__all__ = [
    "CountDocRepo",
]
