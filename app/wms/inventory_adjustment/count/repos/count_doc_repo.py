from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Sequence

from sqlalchemy import case, func, select, text
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

    async def get_active_doc_by_warehouse(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int,
    ) -> CountDoc | None:
        stmt = (
            select(CountDoc)
            .where(
                CountDoc.warehouse_id == int(warehouse_id),
                CountDoc.status.in_(["DRAFT", "FROZEN", "COUNTED"]),
            )
            .order_by(CountDoc.created_at.desc(), CountDoc.id.desc())
            .limit(1)
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def get_doc_detail(
        self,
        session: AsyncSession,
        *,
        doc_id: int,
        include_lot_snapshots: bool = True,
    ) -> CountDoc | None:
        stmt = (
            select(CountDoc)
            .where(CountDoc.id == int(doc_id))
            .options(selectinload(CountDoc.lines))
        )
        if include_lot_snapshots:
            stmt = stmt.options(
                selectinload(CountDoc.lines).selectinload(CountDocLine.lot_snapshots),
            )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def get_doc_line_lot_snapshots_map(
        self,
        session: AsyncSession,
        *,
        doc_id: int,
    ) -> dict[int, list[Any]]:
        rows = await session.execute(
            text(
                """
                SELECT
                  s.id,
                  s.line_id,
                  s.lot_id,
                  s.lot_code_snapshot,
                  s.snapshot_qty_base,
                  s.created_at
                FROM count_doc_line_lot_snapshots s
                JOIN count_doc_lines l
                  ON l.id = s.line_id
                WHERE l.doc_id = :doc_id
                ORDER BY
                  s.line_id ASC,
                  s.snapshot_qty_base DESC,
                  s.lot_id ASC,
                  s.id ASC
                """
            ),
            {"doc_id": int(doc_id)},
        )

        out: dict[int, list[Any]] = {}
        for row in rows.mappings().all():
            obj = SimpleNamespace(
                id=int(row["id"]),
                line_id=int(row["line_id"]),
                lot_id=int(row["lot_id"]),
                lot_code_snapshot=row["lot_code_snapshot"],
                snapshot_qty_base=int(row["snapshot_qty_base"]),
                created_at=row["created_at"],
            )
            out.setdefault(int(obj.line_id), []).append(obj)
        return out

    async def get_line_lot_snapshots(
        self,
        session: AsyncSession,
        *,
        line_id: int,
    ) -> list[Any]:
        rows = await session.execute(
            text(
                """
                SELECT
                  id,
                  line_id,
                  lot_id,
                  lot_code_snapshot,
                  snapshot_qty_base,
                  created_at
                FROM count_doc_line_lot_snapshots
                WHERE line_id = :line_id
                ORDER BY
                  snapshot_qty_base DESC,
                  lot_id ASC,
                  id ASC
                """
            ),
            {"line_id": int(line_id)},
        )

        out: list[Any] = []
        for row in rows.mappings().all():
            out.append(
                SimpleNamespace(
                    id=int(row["id"]),
                    line_id=int(row["line_id"]),
                    lot_id=int(row["lot_id"]),
                    lot_code_snapshot=row["lot_code_snapshot"],
                    snapshot_qty_base=int(row["snapshot_qty_base"]),
                    created_at=row["created_at"],
                )
            )
        return out

    async def list_docs(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int | None = None,
        active_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[int, list[CountDoc]]:
        filters: list[str] = []
        params: dict[str, object] = {
            "limit": int(limit),
            "offset": int(offset),
        }

        if warehouse_id is not None:
            filters.append("warehouse_id = :warehouse_id")
            params["warehouse_id"] = int(warehouse_id)

        if active_only:
            filters.append("status IN ('DRAFT', 'FROZEN', 'COUNTED')")

        where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""

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
        if active_only:
            stmt = stmt.where(CountDoc.status.in_(["DRAFT", "FROZEN", "COUNTED"]))

        items = list((await session.execute(stmt)).scalars().all())
        return total, items

    async def get_doc_line_stats(
        self,
        session: AsyncSession,
        *,
        doc_ids: Sequence[int],
    ) -> dict[int, dict[str, int]]:
        ids = [int(x) for x in doc_ids]
        if not ids:
            return {}

        stmt = (
            select(
                CountDocLine.doc_id.label("doc_id"),
                func.count().label("line_count"),
                func.sum(
                    case(
                        (func.coalesce(CountDocLine.diff_qty_base, 0) != 0, 1),
                        else_=0,
                    )
                ).label("diff_line_count"),
                func.coalesce(func.sum(func.coalesce(CountDocLine.diff_qty_base, 0)), 0).label(
                    "diff_qty_base_total"
                ),
            )
            .where(CountDocLine.doc_id.in_(ids))
            .group_by(CountDocLine.doc_id)
        )

        rows = (await session.execute(stmt)).mappings().all()
        out: dict[int, dict[str, int]] = {}
        for row in rows:
            out[int(row["doc_id"])] = {
                "line_count": int(row["line_count"] or 0),
                "diff_line_count": int(row["diff_line_count"] or 0),
                "diff_qty_base_total": int(row["diff_qty_base_total"] or 0),
            }
        return out

    async def get_posted_event_briefs(
        self,
        session: AsyncSession,
        *,
        event_ids: Sequence[int],
    ) -> dict[int, dict[str, Any]]:
        ids = [int(x) for x in event_ids]
        if not ids:
            return {}

        rows = await session.execute(
            text(
                """
                SELECT
                  id,
                  event_no,
                  event_type,
                  source_type,
                  event_kind,
                  status
                FROM wms_events
                WHERE id = ANY(:event_ids)
                """
            ),
            {"event_ids": ids},
        )
        out: dict[int, dict[str, Any]] = {}
        for row in rows.mappings().all():
            out[int(row["id"])] = dict(row)
        return out

    async def get_base_uom_map(
        self,
        session: AsyncSession,
        *,
        item_ids: Sequence[int],
    ) -> dict[int, dict[str, Any]]:
        ids = [int(x) for x in item_ids]
        if not ids:
            return {}

        rows = await session.execute(
            text(
                """
                SELECT
                  iu.item_id,
                  iu.id AS base_item_uom_id,
                  COALESCE(NULLIF(iu.display_name, ''), iu.uom) AS base_uom_name
                FROM item_uoms iu
                WHERE iu.item_id = ANY(:item_ids)
                  AND iu.is_base IS TRUE
                """
            ),
            {"item_ids": ids},
        )

        out: dict[int, dict[str, Any]] = {}
        for row in rows.mappings().all():
            out[int(row["item_id"])] = {
                "base_item_uom_id": (
                    int(row["base_item_uom_id"])
                    if row.get("base_item_uom_id") is not None
                    else None
                ),
                "base_uom_name": row.get("base_uom_name"),
            }
        return out

    async def freeze_doc_lines_from_current_stock(
        self,
        session: AsyncSession,
        *,
        doc_id: int,
    ) -> tuple[int, int]:
        doc = await self.get_doc(session, doc_id=int(doc_id))
        if doc is None:
            raise LookupError(f"count_doc_not_found:{int(doc_id)}")

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
        counted_by_name_snapshot: str,
        lines: Sequence[dict[str, object]],
    ) -> int:
        updated = 0

        for raw in lines:
            line_id = int(raw["line_id"])
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

            base_uom_row = (
                await session.execute(
                    text(
                        """
                        SELECT
                          iu.id,
                          COALESCE(NULLIF(iu.display_name, ''), iu.uom) AS uom_name_snapshot
                          FROM item_uoms iu
                         WHERE iu.item_id = :item_id
                           AND iu.is_base IS TRUE
                         ORDER BY iu.id ASC
                         LIMIT 1
                        """
                    ),
                    {
                        "item_id": int(line.item_id),
                    },
                )
            ).mappings().first()
            if base_uom_row is None:
                raise LookupError(f"count_doc_line_base_uom_not_found:item_id={int(line.item_id)}")

            counted_qty_base = int(counted_qty_input)
            diff_qty_base = int(counted_qty_base) - int(line.snapshot_qty_base)

            line.counted_item_uom_id = int(base_uom_row["id"])
            line.counted_uom_name_snapshot = str(base_uom_row["uom_name_snapshot"])
            line.counted_ratio_to_base_snapshot = 1
            line.counted_qty_input = int(counted_qty_input)
            line.counted_qty_base = int(counted_qty_base)
            line.diff_qty_base = int(diff_qty_base)

            line.updated_at = datetime.now(timezone.utc)

            updated += 1

        await session.execute(
            text(
                """
                UPDATE count_docs
                   SET counted_by_name_snapshot = :counted_by_name_snapshot,
                       reviewed_by_name_snapshot = NULL
                 WHERE id = :doc_id
                """
            ),
            {
                "doc_id": int(doc_id),
                "counted_by_name_snapshot": str(counted_by_name_snapshot).strip(),
            },
        )

        await session.flush()
        return updated

    async def set_reviewed_by_name_snapshot(
        self,
        session: AsyncSession,
        *,
        doc_id: int,
        reviewed_by_name_snapshot: str,
    ) -> None:
        await session.execute(
            text(
                """
                UPDATE count_docs
                   SET reviewed_by_name_snapshot = :reviewed_by_name_snapshot
                 WHERE id = :doc_id
                """
            ),
            {
                "doc_id": int(doc_id),
                "reviewed_by_name_snapshot": str(reviewed_by_name_snapshot).strip(),
            },
        )

    async def try_mark_doc_counted(
        self,
        session: AsyncSession,
        *,
        doc_id: int,
    ) -> bool:
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
