# app/user/services/user_admin_audit.py
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.wms.shared.services.audit_writer_sync import SyncAuditEventWriter

ADMIN_USER_AUDIT_FLOW = "ADMIN_USER"


class AdminUserAuditService:
    """
    admin 用户治理审计写入服务。

    约束：
    - 只负责把 admin 用户治理相关事件写入 audit_events
    - 不参与主业务判定
    - 写入失败不应影响主业务成功结果（由 SyncAuditEventWriter 内部兜底）
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def write_permission_matrix_updated(
        self,
        *,
        actor_user_id: int,
        target_user_id: int,
        target_username: str,
        before_row: Any,
        after_row: Any,
    ) -> None:
        before_data = self._model_to_dict(before_row)
        after_data = self._model_to_dict(after_row)

        SyncAuditEventWriter.write(
            self.db,
            flow=ADMIN_USER_AUDIT_FLOW,
            event="PERMISSION_MATRIX_UPDATED",
            ref=self._build_ref(target_user_id),
            meta={
                "action": "PERMISSION_MATRIX_UPDATED",
                "actor_user_id": int(actor_user_id),
                "target_user_id": int(target_user_id),
                "target_username": target_username,
                "before": before_data,
                "after": after_data,
                "changed_pages": self._build_changed_pages(
                    before_pages=before_data.get("pages"),
                    after_pages=after_data.get("pages"),
                ),
            },
            auto_commit=True,
        )

    def write_user_status_updated(
        self,
        *,
        actor_user_id: int,
        target_user_id: int,
        target_username: str,
        before_is_active: bool,
        after_is_active: bool,
    ) -> None:
        if bool(before_is_active) == bool(after_is_active):
            return

        SyncAuditEventWriter.write(
            self.db,
            flow=ADMIN_USER_AUDIT_FLOW,
            event="USER_STATUS_UPDATED",
            ref=self._build_ref(target_user_id),
            meta={
                "action": "USER_STATUS_UPDATED",
                "actor_user_id": int(actor_user_id),
                "target_user_id": int(target_user_id),
                "target_username": target_username,
                "before": {
                    "is_active": bool(before_is_active),
                },
                "after": {
                    "is_active": bool(after_is_active),
                },
            },
            auto_commit=True,
        )

    def write_user_deleted(
        self,
        *,
        actor_user_id: int,
        target_user_id: int,
        target_username: str,
        before_snapshot: dict[str, Any],
    ) -> None:
        SyncAuditEventWriter.write(
            self.db,
            flow=ADMIN_USER_AUDIT_FLOW,
            event="USER_DELETED",
            ref=self._build_ref(target_user_id),
            meta={
                "action": "USER_DELETED",
                "actor_user_id": int(actor_user_id),
                "target_user_id": int(target_user_id),
                "target_username": target_username,
                "before": before_snapshot,
            },
            auto_commit=True,
        )

    def write_password_reset(
        self,
        *,
        actor_user_id: int,
        target_user_id: int,
        target_username: str,
    ) -> None:
        SyncAuditEventWriter.write(
            self.db,
            flow=ADMIN_USER_AUDIT_FLOW,
            event="PASSWORD_RESET",
            ref=self._build_ref(target_user_id),
            meta={
                "action": "PASSWORD_RESET",
                "actor_user_id": int(actor_user_id),
                "target_user_id": int(target_user_id),
                "target_username": target_username,
            },
            auto_commit=True,
        )

    def _build_ref(self, target_user_id: int) -> str:
        return f"USER:{int(target_user_id)}"

    def _model_to_dict(self, data: Any) -> dict[str, Any]:
        if data is None:
            return {}
        if hasattr(data, "model_dump"):
            return dict(data.model_dump())
        if hasattr(data, "dict"):
            return dict(data.dict())
        if isinstance(data, dict):
            return dict(data)
        return {"value": data}

    def _build_changed_pages(
        self,
        *,
        before_pages: Any,
        after_pages: Any,
    ) -> dict[str, dict[str, dict[str, bool]]]:
        before_map = before_pages if isinstance(before_pages, dict) else {}
        after_map = after_pages if isinstance(after_pages, dict) else {}

        page_codes = sorted(set(before_map.keys()) | set(after_map.keys()))
        out: dict[str, dict[str, dict[str, bool]]] = {}

        for code in page_codes:
            before_cell = self._normalize_cell(before_map.get(code))
            after_cell = self._normalize_cell(after_map.get(code))
            if before_cell == after_cell:
                continue

            out[code] = {
                "before": before_cell,
                "after": after_cell,
            }

        return out

    def _normalize_cell(self, cell: Any) -> dict[str, bool]:
        if cell is None:
            return {"read": False, "write": False}
        if hasattr(cell, "model_dump"):
            data = cell.model_dump()
            return {
                "read": bool(data.get("read", False)),
                "write": bool(data.get("write", False)),
            }
        if hasattr(cell, "dict"):
            data = cell.dict()
            return {
                "read": bool(data.get("read", False)),
                "write": bool(data.get("write", False)),
            }
        if isinstance(cell, dict):
            return {
                "read": bool(cell.get("read", False)),
                "write": bool(cell.get("write", False)),
            }
        return {"read": False, "write": False}


__all__ = ["AdminUserAuditService", "ADMIN_USER_AUDIT_FLOW"]
