import os
import sys
from uuid import uuid4

# 将项目根目录添加到 Python 路径，确保可以导入 app 模块
sys.path.insert(0, os.path.abspath("."))

# 使用 app.db.deps 中的 get_db
from app.db.deps import get_db
from app.models.inventory_movements import InventoryMovement, MovementType
from app.models.item import Item
from app.models.locations import Location, Warehouse
from app.models.order import Order, OrderLine, OrderType
from app.models.parties import Party, PartyType

# 导入新的库存模型
from app.models.stock import Stock


def seed_database():
    # 使用 context manager 模式来获取 db session
    with next(get_db()) as db:
        try:
            print("开始填充数据库...")

            # 创建供应商和客户
            party_supplier = Party(
                id=str(uuid4()),
                name="供应商 A",
                party_type=PartyType.SUPPLIER,
                address="供应商地址",
            )
            party_customer = Party(
                id=str(uuid4()), name="客户 B", party_type=PartyType.CUSTOMER, address="客户地址"
            )
            db.add_all([party_supplier, party_customer])

            # 创建仓库和库位
            warehouse = Warehouse(id=str(uuid4()), name="主仓库", address="主仓库地址")
            location_a = Location(id=str(uuid4()), name="托盘1", warehouse_id=warehouse.id)
            location_b = Location(id=str(uuid4()), name="shipping_dock", warehouse_id=warehouse.id)
            db.add_all([warehouse, location_a, location_b])

            # 创建物料
            item_a = Item(
                id=str(uuid4()), sku="WL-CATFOOD-001", name="顽皮双拼猫粮", unit_of_measure="KG"
            )
            item_b = Item(id=str(uuid4()), sku="ITEM-002", name="螺母", unit_of_measure="PCS")
            db.add_all([item_a, item_b])

            # 创建采购订单 (PO)
            po = Order(
                id=str(uuid4()),
                order_number="PO-001",
                order_type=OrderType.PURCHASE,
                party_id=party_supplier.id,
            )
            db.add(po)

            # 创建 PO 的订单明细
            po_line = OrderLine(id=str(uuid4()), order_id=po.id, item_sku=item_a.sku, quantity=50.0)
            db.add(po_line)

            # 创建销售订单 (SO)
            so = Order(
                id=str(uuid4()),
                order_number="SO-001",
                order_type=OrderType.SALES,
                party_id=party_customer.id,
            )
            db.add(so)

            # 创建 SO 的订单明细
            so_line = OrderLine(id=str(uuid4()), order_id=so.id, item_sku=item_a.sku, quantity=20.0)
            db.add(so_line)

            # 示例：填充初始库存
            # 在 location_a 创建 100 件 item_a 的库存
            db_stock = Stock(
                id=str(uuid4()),
                item_sku=item_a.sku,
                location_id=location_a.id,
                quantity=100.0,
            )
            db.add(db_stock)

            # 示例：创建一条库存变动记录
            # 记录这 100 件 item_a 的收货
            db_movement = InventoryMovement(
                id=str(uuid4()),
                item_sku=item_a.sku,
                to_location_id=location_a.id,
                quantity=100.0,
                movement_type=MovementType.RECEIPT,
            )
            db.add(db_movement)

            db.commit()
            print("数据库填充完成！")
        except Exception as e:
            db.rollback()
            print(f"填充失败: {e}")


if __name__ == "__main__":
    seed_database()
