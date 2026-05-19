# app/wms/system/write_v1/services/iam_write_service.py
from __future__ import annotations

import secrets

from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.user.models.user import User
from app.wms.system.write_v1.contracts import (
    WmsSystemIamApplyIn,
    WmsSystemIamApplyOut,
    WmsSystemIamPermissionDiffOut,
    WmsSystemIamUserDiffOut,
    WmsSystemIamVerifyOut,
)
from app.wms.system.write_v1.repos import WmsIamWriteRepo

WMS_APP_CODE = "wms"


class WmsIamPayloadError(ValueError):
    pass


class WmsIamPermissionNotFoundError(ValueError):
    pass


def _strip(value: str | None) -> str:
    return (value or "").strip()


def _optional_strip(value: str | None) -> str | None:
    text = _strip(value)
    return text or None


def _disabled_password_hash() -> str:
    return get_password_hash(secrets.token_urlsafe(48))


class NormalizedIamPayload:
    def __init__(
        self,
        *,
        users: dict[str, dict[str, object]],
        desired_permissions_by_username: dict[str, set[str]],
    ) -> None:
        self.users = users
        self.desired_permissions_by_username = desired_permissions_by_username

    @property
    def usernames(self) -> set[str]:
        return set(self.users)

    @property
    def permission_codes(self) -> set[str]:
        out: set[str] = set()
        for codes in self.desired_permissions_by_username.values():
            out.update(codes)
        return out


class WmsIamWriteService:
    """
    Apply and verify WMS local user IAM runtime projection for ERP.

    Boundary:
    - ERP calls this service through /system/write/v1.
    - ERP owns user and user-permission assignment decisions.
    - WMS keeps users / user_permissions as local runtime execution tables.
    - This service does not create unknown permissions.
    - This service does not write page_registry / page_route_prefixes.
    """

    def __init__(
        self,
        db: Session,
        repo: WmsIamWriteRepo | None = None,
    ) -> None:
        self.repo = repo or WmsIamWriteRepo(db)

    def apply(self, payload: WmsSystemIamApplyIn) -> WmsSystemIamApplyOut:
        normalized = self._normalize_payload(payload)
        permissions_by_code = self.repo.list_permissions_by_codes(normalized.permission_codes)
        self._ensure_permissions_exist(normalized.permission_codes, permissions_by_code)

        for username, user_payload in normalized.users.items():
            user = self.repo.get_user_by_username(username)
            if user is None:
                user = User(
                    username=username,
                    password_hash=_disabled_password_hash(),
                    is_active=bool(user_payload["is_active"]),
                    full_name=user_payload["full_name"],
                    phone=user_payload["phone"],
                    email=user_payload["email"],
                )
                self.repo.add(user)
                self.repo.flush()
            else:
                user.is_active = bool(user_payload["is_active"])
                user.full_name = user_payload["full_name"]
                user.phone = user_payload["phone"]
                user.email = user_payload["email"]
                self.repo.flush()

            desired_codes = normalized.desired_permissions_by_username.get(username, set())
            desired_permission_ids = [
                int(permissions_by_code[permission_code].id)
                for permission_code in sorted(desired_codes)
            ]
            self.repo.replace_user_permissions(
                user_id=int(user.id),
                permission_ids=desired_permission_ids,
            )

        self.repo.commit()

        verify = self.verify(payload)
        return WmsSystemIamApplyOut(
            **verify.model_dump(),
            applied=True,
        )

    def verify(self, payload: WmsSystemIamApplyIn) -> WmsSystemIamVerifyOut:
        normalized = self._normalize_payload(payload)
        permissions_by_code = self.repo.list_permissions_by_codes(normalized.permission_codes)
        users_by_username = self.repo.list_users_by_usernames(normalized.usernames)

        missing_users = sorted(username for username in normalized.usernames if username not in users_by_username)
        missing_permission_codes = sorted(
            permission_code
            for permission_code in normalized.permission_codes
            if permission_code not in permissions_by_code
        )

        mismatched_users: list[WmsSystemIamUserDiffOut] = []
        missing_user_permissions: list[WmsSystemIamPermissionDiffOut] = []
        extra_user_permissions: list[WmsSystemIamPermissionDiffOut] = []

        for username, expected in normalized.users.items():
            user = users_by_username.get(username)
            if user is None:
                continue

            self._append_user_mismatches(
                mismatched_users=mismatched_users,
                username=username,
                user=user,
                expected=expected,
            )

            desired_codes = normalized.desired_permissions_by_username.get(username, set())
            actual_codes = self.repo.list_permission_codes_for_user(int(user.id))

            for permission_code in sorted(desired_codes - actual_codes):
                missing_user_permissions.append(
                    WmsSystemIamPermissionDiffOut(
                        username=username,
                        permission_code=permission_code,
                    )
                )

            for permission_code in sorted(actual_codes - desired_codes):
                extra_user_permissions.append(
                    WmsSystemIamPermissionDiffOut(
                        username=username,
                        permission_code=permission_code,
                    )
                )

        verified = not (
            missing_users
            or missing_permission_codes
            or mismatched_users
            or missing_user_permissions
            or extra_user_permissions
        )

        return WmsSystemIamVerifyOut(
            app_code=WMS_APP_CODE,
            verified=verified,
            user_count=len(normalized.users),
            desired_permission_count=sum(
                len(codes) for codes in normalized.desired_permissions_by_username.values()
            ),
            missing_users=missing_users,
            missing_permission_codes=missing_permission_codes,
            mismatched_users=mismatched_users,
            missing_user_permissions=missing_user_permissions,
            extra_user_permissions=extra_user_permissions,
        )

    def _normalize_payload(self, payload: WmsSystemIamApplyIn) -> NormalizedIamPayload:
        users: dict[str, dict[str, object]] = {}
        for user in payload.users:
            username = _strip(user.username)
            if not username:
                raise WmsIamPayloadError("wms_iam_username_required")
            if username in users:
                raise WmsIamPayloadError("wms_iam_duplicate_username")

            users[username] = {
                "username": username,
                "full_name": _optional_strip(user.full_name),
                "phone": _optional_strip(user.phone),
                "email": _optional_strip(user.email),
                "is_active": bool(user.is_active),
            }

        desired_permissions_by_username: dict[str, set[str]] = {
            username: set()
            for username in users
        }

        for user_permission in payload.user_permissions:
            username = _strip(user_permission.username)
            permission_code = _strip(user_permission.permission_code)

            if username not in users:
                raise WmsIamPayloadError("wms_iam_user_permission_unknown_username")
            if not permission_code:
                raise WmsIamPayloadError("wms_iam_permission_code_required")

            if bool(user_permission.is_active):
                desired_permissions_by_username.setdefault(username, set()).add(permission_code)

        return NormalizedIamPayload(
            users=users,
            desired_permissions_by_username=desired_permissions_by_username,
        )

    def _ensure_permissions_exist(
        self,
        permission_codes: set[str],
        permissions_by_code: dict[str, object],
    ) -> None:
        missing = sorted(permission_code for permission_code in permission_codes if permission_code not in permissions_by_code)
        if missing:
            raise WmsIamPermissionNotFoundError(
                "wms_iam_permission_not_found: " + ",".join(missing)
            )

    def _append_user_mismatches(
        self,
        *,
        mismatched_users: list[WmsSystemIamUserDiffOut],
        username: str,
        user: User,
        expected: dict[str, object],
    ) -> None:
        fields = (
            ("is_active", bool(getattr(user, "is_active", True)), bool(expected["is_active"])),
            ("full_name", _optional_strip(getattr(user, "full_name", None)), expected["full_name"]),
            ("phone", _optional_strip(getattr(user, "phone", None)), expected["phone"]),
            ("email", _optional_strip(getattr(user, "email", None)), expected["email"]),
        )

        for field_name, actual, expected_value in fields:
            if actual != expected_value:
                mismatched_users.append(
                    WmsSystemIamUserDiffOut(
                        username=username,
                        field_name=field_name,
                        expected=expected_value,
                        actual=actual,
                    )
                )


__all__ = [
    "WMS_APP_CODE",
    "WmsIamPayloadError",
    "WmsIamPermissionNotFoundError",
    "WmsIamWriteService",
]
