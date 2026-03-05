# app/services/fsku_service_mapper.py
from __future__ import annotations

from app.api.schemas.fsku import FskuComponentOut, FskuDetailOut
from app.models.fsku import Fsku, FskuComponent


def to_detail(f: Fsku, components: list[FskuComponent]) -> FskuDetailOut:
    out_components = [FskuComponentOut(item_id=c.item_id, qty=int(c.qty), role=c.role) for c in components]
    return FskuDetailOut(
        id=f.id,
        code=f.code,
        name=f.name,
        shape=f.shape,
        status=f.status,
        published_at=f.published_at,
        retired_at=f.retired_at,
        created_at=f.created_at,
        updated_at=f.updated_at,
        components=out_components,
    )
