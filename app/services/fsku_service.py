# app/services/fsku_service.py
from __future__ import annotations

from sqlalchemy.orm import Session

from app.api.schemas.fsku import FskuComponentIn, FskuDetailOut, FskuListOut
from app.services.fsku_service_errors import FskuBadInput, FskuConflict, FskuNotFound
from app.services.fsku_service_read import get_detail as _get_detail
from app.services.fsku_service_read import list_fskus as _list_fskus
from app.services.fsku_service_write import (
    create_draft as _create_draft,
    publish as _publish,
    replace_components_draft as _replace_components_draft,
    retire as _retire,
    unretire as _unretire,
    update_name as _update_name,
)


class FskuService:
    # 兼容旧引用名（router 捕获的是 FskuService.NotFound/Conflict/BadInput）
    NotFound = FskuNotFound
    Conflict = FskuConflict
    BadInput = FskuBadInput

    def __init__(self, db: Session):
        self.db = db

    def create_draft(self, *, name: str, code: str | None, shape: str | None) -> FskuDetailOut:
        return _create_draft(self.db, name=name, code=code, shape=shape)

    def list_fskus(self, *, query: str | None, status: str | None, limit: int, offset: int) -> FskuListOut:
        return _list_fskus(self.db, query=query, status=status, limit=limit, offset=offset)

    def get_detail(self, fsku_id: int) -> FskuDetailOut | None:
        return _get_detail(self.db, fsku_id)

    def update_name(self, *, fsku_id: int, name: str) -> FskuDetailOut:
        return _update_name(self.db, fsku_id=fsku_id, name=name)

    def replace_components_draft(self, *, fsku_id: int, components: list[FskuComponentIn]) -> FskuDetailOut:
        return _replace_components_draft(self.db, fsku_id=fsku_id, components=components)

    def publish(self, fsku_id: int) -> FskuDetailOut:
        return _publish(self.db, fsku_id)

    def retire(self, fsku_id: int) -> FskuDetailOut:
        return _retire(self.db, fsku_id)

    def unretire(self, fsku_id: int) -> FskuDetailOut:
        return _unretire(self.db, fsku_id)
