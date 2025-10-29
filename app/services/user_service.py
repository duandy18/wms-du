# app/services/user_service.py
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import exc
from sqlalchemy.orm import Session, joinedload

from .security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.models.permission import Permission
from app.models.role import Role
from app.models.user import User


# ---- 领域异常 ----
class AuthorizationError(Exception):
    """权限不足"""


class DuplicateUserError(Exception):
    """用户名已存在"""


class NotFoundError(Exception):
    """实体不存在"""


class UserService:
    """
    v1.0 强契约版用户服务（同步 Session）：
    - 显式事务边界：成功后 commit，异常时 rollback
    - 输入校验与幂等：创建用户前检查重复；赋权/撤权安全幂等
    - Token 仅作为“访问令牌”颁发/解析，不在此处做持久化黑名单
    """

    def __init__(self, db_session: Session):
        self.db: Session = db_session

    # ---------------------------------------------------------------------
    # 用户
    # ---------------------------------------------------------------------

    def get_user_by_username(self, username: str) -> Optional[User]:
        return (
            self.db.query(User)
            .options(joinedload(User.role).joinedload(Role.permissions))
            .filter(User.username == username)
            .first()
        )

    def create_user(self, username: str, password: str, role_id: int) -> User:
        """
        创建新用户并分配角色；若用户名重复，抛 DuplicateUserError。
        """
        try:
            existed = self.db.query(User.id).filter(User.username == username).first()
            if existed:
                raise DuplicateUserError("用户名已存在")

            role = self.db.query(Role).filter(Role.id == role_id).first()
            if not role:
                raise NotFoundError("角色不存在")

            user = User(
                username=username.strip(),
                hashed_password=hash_password(password),
                role_id=role_id,
            )
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
            return user
        except (DuplicateUserError, NotFoundError):
            self.db.rollback()
            raise
        except exc.SQLAlchemyError as e:
            self.db.rollback()
            raise e

    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """
        校验用户密码，成功返回 User；失败返回 None（不抛错）。
        """
        user = self.db.query(User).filter(User.username == username).first()
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    def change_password(self, user_id: int, old_password: str, new_password: str) -> None:
        """
        修改密码：校验旧密码，成功后写入新 hash。
        """
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                raise NotFoundError("用户不存在")
            if not verify_password(old_password, user.hashed_password):
                raise AuthorizationError("旧密码不正确")
            user.hashed_password = hash_password(new_password)
            self.db.commit()
        except (NotFoundError, AuthorizationError):
            self.db.rollback()
            raise
        except exc.SQLAlchemyError as e:
            self.db.rollback()
            raise e

    # ---------------------------------------------------------------------
    # Token
    # ---------------------------------------------------------------------

    def create_token_for_user(self, user: User, *, expires_in: Optional[int] = None) -> str:
        """
        为用户创建访问令牌；可选传入过期秒数（None 则按默认）。
        """
        data = {"sub": user.username}
        token = create_access_token(data=data, expires_in=expires_in)
        return token

    def get_user_from_token(self, token: str) -> Optional[User]:
        """
        解析访问令牌并返回用户；无效/过期则返回 None。
        """
        payload = decode_access_token(token)
        if not payload or "sub" not in payload:
            return None
        username = payload.get("sub")
        return self.db.query(User).filter(User.username == username).first()

    # ---------------------------------------------------------------------
    # 权限/角色
    # ---------------------------------------------------------------------

    def get_user_permissions(self, user: User) -> List[str]:
        """
        读取用户全部权限名称列表（去重）。
        """
        if not user or not user.role_id:
            return []
        rows = (
            self.db.query(Permission.name)
            .join(Role.permissions)
            .filter(Role.id == user.role_id)
            .all()
        )
        # rows: List[Tuple[str]], 做去重并保持稳定顺序
        seen, out = set(), []
        for (name,) in rows:
            if name not in seen:
                seen.add(name)
                out.append(name)
        return out

    def check_permission(self, user: User, required_permissions: List[str], *, any_of: bool = True) -> bool:
        """
        鉴权：
          - any_of=True（默认）：用户具备任意一个即可通过
          - any_of=False：用户必须同时具备全部权限
        不满足要求则抛 AuthorizationError。
        """
        perms = set(self.get_user_permissions(user))
        req = set(required_permissions or [])
        if not req:
            return True
        ok = (len(perms & req) > 0) if any_of else (req.issubset(perms))
        if not ok:
            raise AuthorizationError("你没有访问该资源的权限")
        return True

    def assign_role_to_user(self, user_id: int, role_id: int) -> None:
        """
        为用户分配角色；用户或角色不存在将抛 NotFoundError。
        """
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                raise NotFoundError("用户不存在")
            role = self.db.query(Role).filter(Role.id == role_id).first()
            if not role:
                raise NotFoundError("角色不存在")
            user.role_id = role_id
            self.db.commit()
        except NotFoundError:
            self.db.rollback()
            raise
        except exc.SQLAlchemyError as e:
            self.db.rollback()
            raise e

    def add_permission_to_role(self, role_id: int, permission_name: str) -> None:
        """
        为角色增加权限（幂等：若已存在则忽略）。
        """
        try:
            role = self.db.query(Role).filter(Role.id == role_id).first()
            if not role:
                raise NotFoundError("角色不存在")
            perm = self.db.query(Permission).filter(Permission.name == permission_name).first()
            if not perm:
                raise NotFoundError("权限不存在")
            if perm not in role.permissions:
                role.permissions.append(perm)
            self.db.commit()
        except NotFoundError:
            self.db.rollback()
            raise
        except exc.SQLAlchemyError as e:
            self.db.rollback()
            raise e

    def remove_permission_from_role(self, role_id: int, permission_name: str) -> None:
        """
        从角色移除权限（幂等：若不存在则忽略）。
        """
        try:
            role = self.db.query(Role).filter(Role.id == role_id).first()
            if not role:
                raise NotFoundError("角色不存在")
            perm = self.db.query(Permission).filter(Permission.name == permission_name).first()
            if not perm:
                # 权限不存在，视为已移除
                self.db.commit()
                return
            if perm in role.permissions:
                role.permissions.remove(perm)
            self.db.commit()
        except NotFoundError:
            self.db.rollback()
            raise
        except exc.SQLAlchemyError as e:
            self.db.rollback()
            raise e
