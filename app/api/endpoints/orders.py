# app/api/endpoints/orders.py
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, get_order_service
from app.schemas.order import OrderCreate, OrderOut, OrderStatusUpdate
from app.services.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post(
    "",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
    summary="创建一个新订单",
)
def create_order(
    order_in: OrderCreate,
    order_service: OrderService = Depends(get_order_service),
    current_user: dict = Depends(get_current_user),
):
    """
    创建一个新的订单。
    当前为开发模式：未做权限验证。
    """
    try:
        return order_service.create_order(order_in)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/{order_id}/complete",
    response_model=OrderOut,
    summary="完成订单并自动生成库存流水",
)
def complete_order(
    order_id: int,
    order_service: OrderService = Depends(get_order_service),
    current_user: dict = Depends(get_current_user),
):
    """
    将订单标记为“完成”，并触发库存更新。
    """
    try:
        return order_service.complete_order(order_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put(
    "/{order_id}/status",
    response_model=OrderOut,
    summary="更新订单状态",
)
def update_order_status(
    order_id: int,
    status_update: OrderStatusUpdate,
    order_service: OrderService = Depends(get_order_service),
    current_user: dict = Depends(get_current_user),
):
    """
    更新订单状态。
    """
    try:
        return order_service.update_order_status(order_id, status_update)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
