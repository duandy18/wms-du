# app/wms/system/write_v1/repos/iam_write_repo.py
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.user.models.permission import Permission
from app.user.models.user import User, user_permissions


class WmsIamWriteSaveError(RuntimeError):
    pass


class WmsIamWriteRepo:
    """
    WMS IAM write-v1 repository.

    Boundary:
    - Writes only users / user_permissions runtime tables.
    - Reads permissions only to validate WMS-owned permission codes.
    - Never writes permissions / page_registry / page_route_prefixes.
    - Never writes ERP tables or other systems.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_user_by_username(self, username: str) -> User | None:
        return self.db.query(User).filter(User.username == username).one_or_none()

    def list_users_by_usernames(self, usernames: Iterable[str]) -> dict[str, User]:
        names = sorted({name for name in usernames if name})
        if not names:
            return {}
        rows = self.db.query(User).filter(User.username.in_(names)).all()
        return {str(row.username): row for row in rows}

    def list_permissions_by_codes(self, permission_codes: Iterable[str]) -> dict[str, Permission]:
        codes = sorted({code for code in permission_codes if code})
        if not codes:
            return {}
        rows = self.db.query(Permission).filter(Permission.name.in_(codes)).all()
        return {str(row.name): row for row in rows}

    def list_permission_codes_for_user(self, user_id: int) -> set[str]:
        rows = (
            self.db.query(Permission.name)
            .join(user_permissions, Permission.id == user_permissions.c.permission_id)
            .filter(user_permissions.c.user_id == int(user_id))
            .order_by(Permission.name.asc())
            .all()
        )
        return {str(name) for (name,) in rows if name}

    def replace_user_permissions(self, *, user_id: int, permission_ids: Iterable[int]) -> None:
        unique_permission_ids = sorted({int(permission_id) for permission_id in permission_ids})
        self.db.execute(user_permissions.delete().where(user_permissions.c.user_id == int(user_id)))
        for permission_id in unique_permission_ids:
            self.db.execute(
                user_permissions.insert().values(
                    user_id=int(user_id),
                    permission_id=int(permission_id),
                )
            )

    def add(self, row: object) -> None:
        self.db.add(row)

    def flush(self) -> None:
        try:
            self.db.flush()
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise WmsIamWriteSaveError("wms_iam_write_flush_failed") from exc

    def commit(self) -> None:
        try:
            self.db.commit()
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise WmsIamWriteSaveError("wms_iam_write_commit_failed") from exc

    def refresh(self, row: object) -> None:
        self.db.refresh(row)


__all__ = [
    "WmsIamWriteRepo",
    "WmsIamWriteSaveError",
]
