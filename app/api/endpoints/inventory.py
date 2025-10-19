# app/api/endpoints/inventory.py


from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user

# 导入服务层和依赖
from app.db.deps import get_db

# 导入 Pydantic 模型
from app.schemas.inventory import (
    InventoryMovementCreate,
    InventoryMovementOut,
    StockOnHandOut,
)
from app.services.inventory_service import InventoryService
from app.services.user_service import AuthorizationError, UserService

router = APIRouter()


# 依赖注入函数
def get_inventory_service(db: Session = Depends(get_db)):
    return InventoryService(db)


def get_user_service(db: Session = Depends(get_db)):
    return UserService(db)


@router.post(
    "/inventory/movements",
    response_model=InventoryMovementOut,
    status_code=status.HTTP_201_CREATED,
)
def create_inventory_movement(
    movement_in: InventoryMovementCreate,
    inv_service: InventoryService = Depends(get_inventory_service),
    user_service: UserService = Depends(get_user_service),
    current_user: dict = Depends(get_current_user),
):
    """
    创建一个新的库存流水记录。
    """
    try:
        user_service.check_permission(current_user, ["create_inventory_movement"])
        return inv_service.create_movement(movement_in)
    except AuthorizationError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="你没有执行此操作的权限")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/inventory/movements", response_model=list[InventoryMovementOut])
def get_all_inventory_movements(
    inv_service: InventoryService = Depends(get_inventory_service),
    user_service: UserService = Depends(get_user_service),
    current_user: dict = Depends(get_current_user),
):
    """
    获取所有库存流水记录的列表。
    """
    try:
        user_service.check_permission(current_user, ["read_inventory_movements"])
        return inv_service.get_all_movements()
    except AuthorizationError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="你没有执行此操作的权限")


@router.get("/inventory/stock_on_hand", response_model=list[StockOnHandOut])
def get_stock_on_hand(
    inv_service: InventoryService = Depends(get_inventory_service),
    user_service: UserService = Depends(get_user_service),
    current_user: dict = Depends(get_current_user),
):
    """
    获取每个库位上每个物料的当前库存总量。
    """
    try:
        user_service.check_permission(current_user, ["read_stock_on_hand"])
        return inv_service.get_stock_on_hand()
    except AuthorizationError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="你没有执行此操作的权限")
