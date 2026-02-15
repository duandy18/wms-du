# app/services/fsku_service_read.py
from __future__ import annotations

from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.schemas.fsku import FskuDetailOut, FskuListItem, FskuListOut
from app.models.fsku import Fsku, FskuComponent
from app.services.fsku_service_mapper import to_detail


def get_detail(db: Session, fsku_id: int) -> FskuDetailOut | None:
    obj = db.get(Fsku, fsku_id)
    if obj is None:
        return None
    comps = db.scalars(select(FskuComponent).where(FskuComponent.fsku_id == fsku_id)).all()
    return to_detail(obj, comps)


def _is_test_store(db: Session, store_id: int) -> bool:
    v = db.execute(
        text(
            """
            SELECT EXISTS (
              SELECT 1
                FROM platform_test_shops pts
               WHERE pts.store_id = :sid
                 AND pts.code = 'DEFAULT'
            ) AS is_test
            """
        ),
        {"sid": int(store_id)},
    ).scalar()
    return bool(v or False)


def list_fskus(
    db: Session,
    *,
    query: str | None,
    status: str | None,
    store_id: int | None,
    limit: int,
    offset: int,
) -> FskuListOut:
    is_test_store = False
    if store_id is not None:
        is_test_store = _is_test_store(db, int(store_id))

    # --- WHERE 片段（同口径复用）---
    where_sql = " WHERE 1=1 "
    params: dict[str, Any] = {"limit": int(limit), "offset": int(offset)}

    # PROD 店铺：过滤测试 FSKU（命中 DEFAULT test set）
    if store_id is not None and not is_test_store:
        where_sql += """
        AND NOT EXISTS (
          SELECT 1
            FROM fsku_components c2
            JOIN item_test_set_items tsi ON tsi.item_id = c2.item_id
            JOIN item_test_sets ts ON ts.id = tsi.set_id AND ts.code = 'DEFAULT'
           WHERE c2.fsku_id = f.id
        )
        """

    if query:
        params["q"] = f"%{query.strip()}%"
        where_sql += " AND (f.name ILIKE :q OR f.code ILIKE :q) "

    if status:
        params["status"] = status
        where_sql += " AND f.status = :status "

    # --- total（与 items 同口径）---
    count_sql = (
        """
        SELECT COUNT(*) FROM (
          SELECT f.id
            FROM fskus f
        """
        + where_sql
        + """
           GROUP BY f.id
        ) t
        """
    )
    total = int(db.execute(text(count_sql), params).scalar() or 0)

    # --- list ---
    list_sql = (
        """
        SELECT
          f.id,
          f.code,
          f.name,
          f.shape,
          f.status,
          f.updated_at,
          f.published_at,
          f.retired_at,
          COALESCE(
            STRING_AGG(
              (i.sku || '×' || (c.qty::int)::text || '(' || c.role || ')'),
              ' + '
              ORDER BY c.role, i.sku
            ),
            ''
          ) AS components_summary,
          COALESCE(
            STRING_AGG(
              (COALESCE(i.name, i.sku) || '×' || (c.qty::int)::text || '(' || c.role || ')'),
              ' + '
              ORDER BY c.role, COALESCE(i.name, i.sku)
            ),
            ''
          ) AS components_summary_name
        FROM fskus f
        LEFT JOIN fsku_components c ON c.fsku_id = f.id
        LEFT JOIN items i ON i.id = c.item_id
        """
        + where_sql
        + """
        GROUP BY f.id
        ORDER BY f.updated_at DESC
        LIMIT :limit OFFSET :offset
        """
    )

    rows = db.execute(text(list_sql), params).mappings().all()

    items = [
        FskuListItem(
            id=int(r["id"]),
            code=str(r["code"]),
            name=str(r["name"]),
            shape=str(r["shape"]),
            status=str(r["status"]),
            updated_at=r["updated_at"],
            published_at=r["published_at"],
            retired_at=r["retired_at"],
            components_summary=str(r["components_summary"] or ""),
            components_summary_name=str(r["components_summary_name"] or ""),
        )
        for r in rows
    ]
    return FskuListOut(items=items, total=total, limit=limit, offset=offset)
