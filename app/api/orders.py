from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.models.inventory import InventoryMovement, MovementType
from app.models.items import Item
from app.models.locations import Location
from app.models.orders import Order, OrderLine, OrderStatus, OrderType
from app.models.parties import Party
from app.schemas.orders import OrderCreate, OrderOut, OrderStatusUpdate, OrderUpdate

router = APIRouter()


@router.post(
    "/orders",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
    summary="创建一个新订单",
)
def create_order(order_in: OrderCreate, db: Session = Depends(get_db)):
    """
    创建一个新的订单，包括采购订单(PO)或销售订单(SO)。
    """
    # 验证 party_id 是否存在
    party = db.query(Party).filter(Party.id == order_in.party_id).first()
    if not party:
        raise HTTPException(status_code=404, detail="Party not found")

    # 创建订单主表
    db_order = Order(
        id=str(uuid4()),
        order_number=order_in.order_number,
        order_type=order_in.order_type,
        party_id=order_in.party_id,
    )
    db.add(db_order)

    # 创建订单行
    for line_in in order_in.order_lines:
        # 验证 item_sku 是否存在
        item = db.query(Item).filter(Item.sku == line_in.item_sku).first()
        if not item:
            raise HTTPException(
                status_code=404, detail=f"Item with SKU '{line_in.item_sku}' not found"
            )

        db_line = OrderLine(
            id=str(uuid4()),
            order_id=db_order.id,
            item_sku=line_in.item_sku,
            quantity=line_in.quantity,
        )
        db.add(db_line)

    db.commit()
    db.refresh(db_order)
    return db_order


@router.get("/orders", response_model=list[OrderOut], summary="获取所有订单")
def get_all_orders(db: Session = Depends(get_db)):
    """
    获取数据库中所有订单的列表，并包含它们的订单明细。
    """
    # 使用 joinedload 预先加载 order_lines，避免 N+1 查询问题
    return db.query(Order).options(joinedload(Order.order_lines)).all()


@router.get("/orders/{order_id}", response_model=OrderOut, summary="通过ID获取单个订单")
def get_order(order_id: str, db: Session = Depends(get_db)):
    """
    通过订单ID获取单个订单的详细信息。
    """
    order = (
        db.query(Order).options(joinedload(Order.order_lines)).filter(Order.id == order_id).first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.put("/orders/{order_id}", response_model=OrderOut, summary="更新订单信息（包括状态）")
def update_order(order_id: str, order_update: OrderUpdate, db: Session = Depends(get_db)):
    """
    通过ID更新一个订单的详细信息，例如修改订单状态或订单号。
    """
    order = (
        db.query(Order).options(joinedload(Order.order_lines)).filter(Order.id == order_id).first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    for field, value in order_update.model_dump(exclude_unset=True).items():
        setattr(order, field, value)

    db.commit()
    db.refresh(order)
    return order


@router.post(
    "/orders/{order_id}/complete", response_model=OrderOut, summary="完成订单并自动生成库存流水"
)
def complete_order(order_id: str, db: Session = Depends(get_db)):
    """
    将一个订单标记为“完成”，并根据订单类型自动生成库存流水。
    - 采购订单(PO) 会创建 "receipt" (收货) 流水。
    - 销售订单(SO) 会创建 "shipment" (发货) 流水。
    """
    # 1. 查找订单
    order = (
        db.query(Order).options(joinedload(Order.order_lines)).filter(Order.id == order_id).first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # 2. 验证订单状态
    if order.status != OrderStatus.CONFIRMED:
        raise HTTPException(
            status_code=400, detail="Order must be in 'CONFIRMED' status to be completed"
        )

    # 3. 遍历订单明细，创建库存流水
    for line in order.order_lines:
        movement_type = None
        from_loc_id = None
        to_loc_id = None

        # 3.1 使用更安全的字符串值比较来判断订单类型
        if order.order_type.value == OrderType.PURCHASE.value:
            movement_type = MovementType.RECEIPT
            location = db.query(Location).filter(Location.name == "托盘1").first()
            if not location:
                raise HTTPException(
                    status_code=500,
                    detail="Location '托盘1' not found in database for a purchase order.",
                )
            to_loc_id = location.id

        elif order.order_type.value == OrderType.SALES.value:
            movement_type = MovementType.SHIPMENT
            location = db.query(Location).filter(Location.name == "shipping_dock").first()
            if not location:
                raise HTTPException(
                    status_code=500,
                    detail="Location 'shipping_dock' not found in database for a sales order.",
                )
            from_loc_id = location.id

        # 3.2 创建 InventoryMovement 记录
        inventory_movement = InventoryMovement(
            id=str(uuid4()),
            item_sku=line.item_sku,
            from_location_id=from_loc_id,
            to_location_id=to_loc_id,
            quantity=line.quantity,
            movement_type=movement_type,
        )
        db.add(inventory_movement)

    # 4. 更新订单状态并提交
    order.status = OrderStatus.COMPLETE
    db.commit()
    db.refresh(order)

    return order


@router.put("/orders/{order_id}/status", response_model=OrderOut, summary="更新订单状态")
def update_order_status(
    order_id: str, status_update: OrderStatusUpdate, db: Session = Depends(get_db)
):
    """
    专门用于更新订单状态的接口，例如从 DRAFT 变为 CONFIRMED。
    """
    order = (
        db.query(Order).options(joinedload(Order.order_lines)).filter(Order.id == order_id).first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = status_update.status
    db.commit()
    db.refresh(order)
    return order
