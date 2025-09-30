from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.models.inventory import InventoryMovement, MovementType
from app.models.items import Item
from app.models.locations import Location
from app.models.orders import Order, OrderLine, OrderStatus, OrderType
from app.models.parties import Party
from app.schemas.orders import OrderCreate, OrderOut, OrderStatusUpdate

router = APIRouter()


@router.post("/orders", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(order_in: OrderCreate, db: Session = Depends(get_db)):
    """
    创建一个新的订单（采购或销售）。
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


@router.get("/orders", response_model=list[OrderOut])
def get_all_orders(db: Session = Depends(get_db)):
    """
    获取所有订单的列表。
    """
    # 使用 joinedload 预先加载 order_lines，避免 N+1 查询问题
    return db.query(Order).options(joinedload(Order.order_lines)).all()


@router.get("/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: str, db: Session = Depends(get_db)):
    """
    通过ID获取单个订单。
    """
    order = (
        db.query(Order).options(joinedload(Order.order_lines)).filter(Order.id == order_id).first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.post("/orders/{order_id}/complete", response_model=OrderOut)
def complete_order(order_id: str, db: Session = Depends(get_db)):
    """
    将一个订单标记为“完成”，并根据订单类型自动生成库存流水。
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

        # 3.1 查找真实库位 ID (修复硬编码问题)
        if order.order_type == OrderType.PURCHASE:
            movement_type = MovementType.RECEIPT
            location = db.query(Location).filter(Location.name == "托盘1").first()
            if not location:
                raise HTTPException(
                    status_code=500, detail="Location '托盘1' not found in database."
                )
            to_loc_id = location.id

        elif order.order_type == OrderType.SALES:
            movement_type = MovementType.SHIPMENT
            location = db.query(Location).filter(Location.name == "shipping_dock").first()
            if not location:
                raise HTTPException(
                    status_code=500, detail="Location 'shipping_dock' not found in database."
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


@router.put("/orders/{order_id}/status", response_model=OrderOut)
def update_order_status(
    order_id: str, status_update: OrderStatusUpdate, db: Session = Depends(get_db)
):
    """
    更新订单的状态。
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
