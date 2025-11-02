# app/api/endpoints/items.py


from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user

# 导入服务层和依赖
from app.db.deps import get_db

# 导入 Pydantic 模型
from app.schemas.item import ItemCreate, ItemOut
from app.services.item_service import ItemService  # 假设存在 ItemService
from app.services.user_service import AuthorizationError, UserService

router = APIRouter()


# 依赖注入函数
def get_item_service(db: Session = Depends(get_db)):
    return ItemService(db)


def get_user_service(db: Session = Depends(get_db)):
    return UserService(db)


@router.post("/items", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
def create_item(
    item_in: ItemCreate,
    item_service: ItemService = Depends(get_item_service),
    user_service: UserService = Depends(get_user_service),
    current_user: dict = Depends(get_current_user),
):
    """
    创建一个新的物料。
    """
    try:
        user_service.check_permission(current_user, ["create_item"])
        return item_service.create_item(item_in.sku, item_in.name, item_in.description)
    except AuthorizationError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="你没有执行此操作的权限")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/items", response_model=list[ItemOut])
def get_all_items(
    item_service: ItemService = Depends(get_item_service),
    user_service: UserService = Depends(get_user_service),
    current_user: dict = Depends(get_current_user),
):
    """
    获取所有物料的列表。
    """
    try:
        user_service.check_permission(current_user, ["read_items"])
        return item_service.get_all_items()
    except AuthorizationError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="你没有执行此操作的权限")


@router.get("/items/{item_sku}", response_model=ItemOut)
def get_item_by_sku(
    item_sku: str,
    item_service: ItemService = Depends(get_item_service),
    user_service: UserService = Depends(get_user_service),
    current_user: dict = Depends(get_current_user),
):
    """
    通过 SKU 获取单个物料。
    """
    try:
        user_service.check_permission(current_user, ["read_items"])
        item = item_service.get_item_by_sku(item_sku)
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")
        return item
    except AuthorizationError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="你没有执行此操作的权限")
