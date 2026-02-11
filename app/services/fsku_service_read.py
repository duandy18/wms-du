# app/services/fsku_service_read.py
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, text
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


def list_fskus(db: Session, *, query: str | None, status: str | None, limit: int, offset: int) -> FskuListOut:
    base = select(Fsku.id)
    if query:
        q = f"%{query.strip()}%"
        base = base.where(Fsku.name.ilike(q) | Fsku.code.ilike(q))
    if status:
        base = base.where(Fsku.status == status)

    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)

    sql = """
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
    WHERE 1=1
    """
    params: dict[str, Any] = {"limit": limit, "offset": offset}

    if query:
        sql += " AND (f.name ILIKE :q OR f.code ILIKE :q) "
        params["q"] = f"%{query.strip()}%"

    if status:
        sql += " AND f.status = :status "
        params["status"] = status

    sql += """
    GROUP BY f.id
    ORDER BY f.updated_at DESC
    LIMIT :limit OFFSET :offset
    """

    rows = db.execute(text(sql), params).mappings().all()

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
