# app/api/endpoints/stock.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user

# 导入服务层和依赖
from app.db.deps import get_db

# 导入 Pydantic 模型
from app.schemas.stock import Stock as StockSchema, StockCreate, StockUpdate
from app.services.stock_service import StockService
from app.services.user_service import AuthorizationError, UserService

router = APIRouter()


# 依赖注入函数
def get_stock_service(db: Session = Depends(get_db)):
    return StockService(db)


def get_user_service(db: Session = Depends(get_db)):
    return UserService(db)


@router.post("/", response_model=StockSchema, status_code=status.HTTP_201_CREATED)
def create_stock_record(
    stock_in: StockCreate,
    stock_service: StockService = Depends(get_stock_service),
    user_service: UserService = Depends(get_user_service),
    current_user: dict = Depends(get_current_user),
):
    """
    创建一个新的库存记录。
    """
    try:
        user_service.check_permission(current_user, ["create_stock"])
        # 将所有业务逻辑和验证移到服务层
        return stock_service.create_stock_record(
            item_sku=stock_in.item_sku,
            location_id=stock_in.location_id,
            batch_number=stock_in.batch_number,
            quantity=stock_in.quantity,
        )
    except AuthorizationError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized.")
    except ValueError as e:
        # 服务层会抛出更具体的错误信息，路由层将其转换为HTTP异常
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/{stock_id}", response_model=StockSchema)
def update_stock_quantity(
    stock_id: str,
    stock_update: StockUpdate,
    stock_service: StockService = Depends(get_stock_service),
    user_service: UserService = Depends(get_user_service),
    current_user: dict = Depends(get_current_user),
):
    """
    更新一个库存记录的数量。
    """
    try:
        user_service.check_permission(current_user, ["update_stock"])
        return stock_service.update_stock_quantity(stock_id, stock_update.quantity)
    except AuthorizationError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized.")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
