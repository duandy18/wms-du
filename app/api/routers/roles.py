# app/api/routers/roles.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_current_user
from app.db.deps import get_db
from app.schemas.role import RoleCreate, RoleOut
from app.services.role_service import RoleService
from app.services.user_service import AuthorizationError, UserService

router = APIRouter(prefix="/roles", tags=["roles"])

def get_role_service(db: Session = Depends(get_db)): return RoleService(db)
def get_user_service(db: Session = Depends(get_db)): return UserService(db)

@router.post("", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
def create_role(role_in: RoleCreate,
                role_service: RoleService = Depends(get_role_service),
                user_service: UserService = Depends(get_user_service),
                current_user: dict = Depends(get_current_user)):
    try:
        user_service.check_permission(current_user, ["create_role"])
        return role_service.create_role(role_in.name, role_in.description)
    except AuthorizationError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized.")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

@router.get("", response_model=list[RoleOut])
def get_all_roles(role_service: RoleService = Depends(get_role_service),
                  user_service: UserService = Depends(get_user_service),
                  current_user: dict = Depends(get_current_user)):
    try:
        user_service.check_permission(current_user, ["read_roles"])
        return role_service.get_all_roles()
    except AuthorizationError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized.")

@router.get("/{role_id}", response_model=RoleOut)
def get_role_by_id(role_id: str,
                   role_service: RoleService = Depends(get_role_service),
                   user_service: UserService = Depends(get_user_service),
                   current_user: dict = Depends(get_current_user)):
    try:
        user_service.check_permission(current_user, ["read_roles"])
        role = role_service.get_role_by_id(role_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found.")
        return role
    except AuthorizationError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized.")

@router.put("/{role_id}/permissions", response_model=RoleOut)
def add_permissions_to_role(role_id: str, permission_ids: list[str],
                            role_service: RoleService = Depends(get_role_service),
                            user_service: UserService = Depends(get_user_service),
                            current_user: dict = Depends(get_current_user)):
    try:
        user_service.check_permission(current_user, ["add_permission_to_role"])
        return role_service.add_permissions_to_role(role_id, permission_ids)
    except AuthorizationError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized.")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
