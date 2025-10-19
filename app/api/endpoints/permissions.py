# app/api/endpoints/permission.py

# 假设存在一个 PermissionService
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user

# 导入服务层和依赖
from app.db.deps import get_db

# 导入 Pydantic 模型
from app.schemas.permission import PermissionCreate, PermissionOut
from app.services.permission_service import PermissionService
from app.services.user_service import AuthorizationError, UserService

router = APIRouter()


# 依赖注入函数
def get_permission_service(db: Session = Depends(get_db)):
    return PermissionService(db)


def get_user_service(db: Session = Depends(get_db)):
    return UserService(db)


@router.post("/", response_model=PermissionOut, status_code=status.HTTP_201_CREATED)
def create_permission(
    permission_in: PermissionCreate,
    perm_service: PermissionService = Depends(get_permission_service),
    user_service: UserService = Depends(get_user_service),
    current_user: dict = Depends(get_current_user),
):
    """
    创建一个新的权限。
    """
    try:
        user_service.check_permission(current_user, ["create_permission"])
        return perm_service.create_permission(permission_in.name)
    except AuthorizationError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized.")
    except ValueError as e:  # 假设服务层在权限已存在时抛出 ValueError
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/", response_model=list[PermissionOut])
def get_all_permissions(
    perm_service: PermissionService = Depends(get_permission_service),
    user_service: UserService = Depends(get_user_service),
    current_user: dict = Depends(get_current_user),
):
    """
    获取所有权限的列表。
    """
    try:
        user_service.check_permission(current_user, ["read_permissions"])
        return perm_service.get_all_permissions()
    except AuthorizationError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized.")


@router.get("/{permission_id}", response_model=PermissionOut)
def get_permission_by_id(
    permission_id: str,
    perm_service: PermissionService = Depends(get_permission_service),
    user_service: UserService = Depends(get_user_service),
    current_user: dict = Depends(get_current_user),
):
    """
    通过 ID 获取一个权限。
    """
    try:
        user_service.check_permission(current_user, ["read_permissions"])
        permission = perm_service.get_permission_by_id(permission_id)
        if not permission:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Permission not found."
            )
        return permission
    except AuthorizationError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized.")
