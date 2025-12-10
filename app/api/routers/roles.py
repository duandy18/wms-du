# app/api/routers/roles.py
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.deps import get_db
from app.schemas.role import RoleCreate, RoleOut
from app.services.role_service import RoleService
from app.services.user_service import AuthorizationError, UserService

router = APIRouter(prefix="/roles", tags=["roles"])


def get_role_service(db: Session = Depends(get_db)) -> RoleService:
  return RoleService(db)


def get_user_service(db: Session = Depends(get_db)) -> UserService:
  return UserService(db)


class RolePermissionsBody(BaseModel):
  """
  /roles/{role_id}/permissions 的请求体：

  {
    "permission_ids": ["1", "2", "3"]
  }
  """

  permission_ids: list[str]


@router.post("", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
def create_role(
  role_in: RoleCreate,
  role_service: RoleService = Depends(get_role_service),
  user_service: UserService = Depends(get_user_service),
  current_user=Depends(get_current_user),
):
  """
  创建角色。

  需要权限: system.role.manage
  """
  try:
    user_service.check_permission(current_user, ["system.role.manage"])
    return role_service.create_role(role_in.name, role_in.description)
  except AuthorizationError:
    raise HTTPException(
      status_code=status.HTTP_403_FORBIDDEN,
      detail="Not authorized.",
    )
  except ValueError as e:
    raise HTTPException(
      status_code=status.HTTP_409_CONFLICT,
      detail=str(e),
    )


@router.get("", response_model=list[RoleOut])
def get_all_roles(
  role_service: RoleService = Depends(get_role_service),
  user_service: UserService = Depends(get_user_service),
  current_user=Depends(get_current_user),
):
  """
  获取全部角色列表。

  需要权限: system.role.manage
  """
  try:
    user_service.check_permission(current_user, ["system.role.manage"])
    return role_service.get_all_roles()
  except AuthorizationError:
    raise HTTPException(
      status_code=status.HTTP_403_FORBIDDEN,
      detail="Not authorized.",
    )


@router.get("/{role_id}", response_model=RoleOut)
def get_role_by_id(
  role_id: str,
  role_service: RoleService = Depends(get_role_service),
  user_service: UserService = Depends(get_user_service),
  current_user=Depends(get_current_user),
):
  """
  按 ID 获取角色详情。

  需要权限: system.role.manage
  """
  try:
    user_service.check_permission(current_user, ["system.role.manage"])
    role = role_service.get_role_by_id(role_id)
    if not role:
      raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Role not found.",
      )
    return role
  except AuthorizationError:
    raise HTTPException(
      status_code=status.HTTP_403_FORBIDDEN,
      detail="Not authorized.",
    )


@router.put("/{role_id}/permissions", response_model=RoleOut)
@router.patch("/{role_id}/permissions", response_model=RoleOut)
def set_role_permissions(
  role_id: str,
  body: RolePermissionsBody = Body(...),
  role_service: RoleService = Depends(get_role_service),
  user_service: UserService = Depends(get_user_service),
  current_user=Depends(get_current_user),
):
  """
  为某个角色批量绑定权限（幂等覆盖）。

  请求示例：
      PATCH /roles/1/permissions
      {
        "permission_ids": ["1", "2", "3"]
      }

  需要权限: system.role.manage
  """
  try:
    user_service.check_permission(current_user, ["system.role.manage"])
    permission_ids = body.permission_ids or []
    return role_service.add_permissions_to_role(role_id, permission_ids)
  except AuthorizationError:
    raise HTTPException(
      status_code=status.HTTP_403_FORBIDDEN,
      detail="Not authorized.",
    )
  except ValueError as e:
    raise HTTPException(
      status_code=status.HTTP_404_NOT_FOUND,
      detail=str(e),
    )
  except Exception as e:
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail=str(e),
    )
