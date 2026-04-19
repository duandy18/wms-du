# app/wms/outbound/repos/manual_doc_repo.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

UTC = timezone.utc


def _gen_doc_no() -> str:
    return f"MOB-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6].upper()}"


async def create_manual_doc(
    session: AsyncSession,
    *,
    warehouse_id: int,
    doc_type: str,
    recipient_name: str,
    recipient_type: str | None,
    recipient_note: str | None,
    remark: str | None,
    created_by: int | None,
    lines: List[Dict[str, Any]],
) -> int:
    row = (
        await session.execute(
            text(
                """
                INSERT INTO manual_outbound_docs (
                  warehouse_id,
                  doc_no,
                  doc_type,
                  status,
                  recipient_name,
                  recipient_type,
                  recipient_note,
                  note,
                  created_by,
                  created_at
                )
                VALUES (
                  :warehouse_id,
                  :doc_no,
                  :doc_type,
                  'DRAFT',
                  :recipient_name,
                  :recipient_type,
                  :recipient_note,
                  :note,
                  :created_by,
                  now()
                )
                RETURNING id
                """
            ),
            {
                "warehouse_id": int(warehouse_id),
                "doc_no": _gen_doc_no(),
                "doc_type": str(doc_type).strip(),
                "recipient_name": str(recipient_name).strip(),
                "recipient_type": str(recipient_type).strip() if recipient_type else None,
                "recipient_note": str(recipient_note).strip() if recipient_note else None,
                "note": str(remark).strip() if remark else None,
                "created_by": int(created_by) if created_by is not None else None,
            },
        )
    ).first()
    if not row:
        raise ValueError("create_manual_doc_failed")

    doc_id = int(row[0])

    line_no = 1
    for ln in lines:
        await session.execute(
            text(
                """
                INSERT INTO manual_outbound_lines (
                  doc_id,
                  line_no,
                  item_id,
                  requested_qty,
                  note
                )
                VALUES (
                  :doc_id,
                  :line_no,
                  :item_id,
                  :requested_qty,
                  :note
                )
                """
            ),
            {
                "doc_id": doc_id,
                "line_no": int(line_no),
                "item_id": int(ln["item_id"]),
                "requested_qty": int(ln["requested_qty"]),
                "note": str(ln["remark"]).strip() if ln.get("remark") else None,
            },
        )
        line_no += 1

    return doc_id


async def list_manual_docs(
    session: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                      d.id,
                      d.warehouse_id,
                      d.doc_no,
                      d.doc_type,
                      d.status,
                      d.recipient_name,
                      d.recipient_id,
                      d.recipient_type,
                      d.recipient_note,
                      d.note AS remark,
                      d.created_by,
                      d.created_at,
                      d.confirmed_by AS released_by,
                      d.confirmed_at AS released_at,
                      d.canceled_by AS voided_by,
                      d.canceled_at AS voided_at
                    FROM manual_outbound_docs d
                    ORDER BY d.created_at DESC, d.id DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {"limit": int(limit), "offset": int(offset)},
            )
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


async def get_manual_doc_head(
    session: AsyncSession,
    *,
    doc_id: int,
) -> Mapping[str, Any]:
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                      d.id,
                      d.warehouse_id,
                      d.doc_no,
                      d.doc_type,
                      d.status,
                      d.recipient_name,
                      d.recipient_id,
                      d.recipient_type,
                      d.recipient_note,
                      d.note AS remark,
                      d.created_by,
                      d.created_at,
                      d.confirmed_by AS released_by,
                      d.confirmed_at AS released_at,
                      d.canceled_by AS voided_by,
                      d.canceled_at AS voided_at
                    FROM manual_outbound_docs d
                    WHERE d.id = :doc_id
                    LIMIT 1
                    """
                ),
                {"doc_id": int(doc_id)},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise ValueError(f"manual_doc_not_found: id={doc_id}")
    return row


async def get_manual_doc_lines(
    session: AsyncSession,
    *,
    doc_id: int,
) -> List[Dict[str, Any]]:
    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                      l.id,
                      l.line_no,
                      l.item_id,
                      l.requested_qty,
                      l.note AS remark
                    FROM manual_outbound_lines l
                    WHERE l.doc_id = :doc_id
                    ORDER BY l.line_no ASC, l.id ASC
                    """
                ),
                {"doc_id": int(doc_id)},
            )
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


async def release_manual_doc(
    session: AsyncSession,
    *,
    doc_id: int,
    released_by: int | None,
) -> None:
    # 至少一行
    row = (
        await session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM manual_outbound_lines
                WHERE doc_id = :doc_id
                """
            ),
            {"doc_id": int(doc_id)},
        )
    ).first()
    if not row or int(row[0]) <= 0:
        raise ValueError("manual_doc_has_no_lines")

    upd = await session.execute(
        text(
            """
            UPDATE manual_outbound_docs
            SET
              status = 'RELEASED',
              confirmed_by = :released_by,
              confirmed_at = now()
            WHERE id = :doc_id
              AND status = 'DRAFT'
            """
        ),
        {
            "doc_id": int(doc_id),
            "released_by": int(released_by) if released_by is not None else None,
        },
    )
    if upd.rowcount != 1:
        raise ValueError(f"manual_doc_release_reject: id={doc_id}")


async def void_manual_doc(
    session: AsyncSession,
    *,
    doc_id: int,
    voided_by: int | None,
) -> None:
    upd = await session.execute(
        text(
            """
            UPDATE manual_outbound_docs
            SET
              status = 'VOIDED',
              canceled_by = :voided_by,
              canceled_at = now()
            WHERE id = :doc_id
              AND status IN ('DRAFT', 'RELEASED')
            """
        ),
        {
            "doc_id": int(doc_id),
            "voided_by": int(voided_by) if voided_by is not None else None,
        },
    )
    if upd.rowcount != 1:
        raise ValueError(f"manual_doc_void_reject: id={doc_id}")
