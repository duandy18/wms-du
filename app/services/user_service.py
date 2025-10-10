# app/services/user_service.py


from sqlalchemy import exc
from sqlalchemy.orm import Session

from .security import create_access_token, decode_access_token, hash_password, verify_password
from app.models.permission import Permission
from app.models.role import Role
from app.models.user import User


# --- 自定义异常 ---
class AuthorizationError(Exception):
    """自定义异常：授权失败"""

    pass


class UserService:
    def __init__(self, db_session: Session):
        self.db = db_session

    def create_user(self, username: str, password: str, role_id: int):
        """
        创建新用户并为其分配角色。
        """
        try:
            hashed_password = hash_password(password)
            new_user = User(username=username, hashed_password=hashed_password, role_id=role_id)
            self.db.add(new_user)
            self.db.commit()
            self.db.refresh(new_user)
            return new_user
        except exc.SQLAlchemyError as e:
            self.db.rollback()
            raise e

    def authenticate_user(self, username: str, password: str):
        """
        验证用户凭据并返回用户对象。
        """
        user = self.db.query(User).filter(User.username == username).first()
        if not user or not verify_password(password, user.hashed_password):
            return None
        return user

    def create_token_for_user(self, user: User) -> str:
        """
        为用户创建并返回一个访问令牌。
        """
        token = create_access_token(data={"sub": user.username})
        return token

    def get_user_from_token(self, token: str):
        """
        根据访问令牌获取用户对象。
        """
        payload = decode_access_token(token)
        if not payload or "sub" not in payload:
            return None
        username = payload.get("sub")
        user = self.db.query(User).filter(User.username == username).first()
        return user

    def get_user_permissions(self, user: User) -> list[str]:
        """
        获取用户的所有权限。
        """
        if not user or not user.role:
            return []

        permissions = (
            self.db.query(Permission).join(Role.permissions).filter(Role.id == user.role.id).all()
        )

        return [p.name for p in permissions]

    def check_permission(self, user: User, required_permissions: list[str]):
        """
        检查用户是否拥有所需的任何一个权限，如果没有则抛出异常。
        """
        user_permissions = self.get_user_permissions(user)
        if not any(p in user_permissions for p in required_permissions):
            raise AuthorizationError("你没有访问该资源的权限")
        return True

    def assign_role_to_user(self, user_id: int, role_id: int):
        """
        将角色分配给用户。
        """
        try:
            with self.db.begin():
                user = self.db.query(User).filter(User.id == user_id).first()
                if not user:
                    raise ValueError("用户不存在")
                user.role_id = role_id
        except (ValueError, exc.SQLAlchemyError) as e:
            self.db.rollback()
            raise e

    def add_permission_to_role(self, role_id: int, permission_name: str):
        """
        为角色增加权限。
        """
        try:
            with self.db.begin():
                role = self.db.query(Role).filter(Role.id == role_id).first()
                permission = (
                    self.db.query(Permission).filter(Permission.name == permission_name).first()
                )

                if not role:
                    raise ValueError("角色不存在")
                if not permission:
                    raise ValueError("权限不存在")

                if permission in role.permissions:
                    return

                role.permissions.append(permission)
        except (ValueError, exc.SQLAlchemyError) as e:
            self.db.rollback()
            raise e

    def remove_permission_from_role(self, role_id: int, permission_name: str):
        """
        从角色中移除权限。
        """
        try:
            with self.db.begin():
                role = self.db.query(Role).filter(Role.id == role_id).first()
                permission = (
                    self.db.query(Permission).filter(Permission.name == permission_name).first()
                )

                if not role:
                    raise ValueError("角色不存在")
                if not permission:
                    return

                if permission in role.permissions:
                    role.permissions.remove(permission)
        except (ValueError, exc.SQLAlchemyError) as e:
            self.db.rollback()
            raise e
