# app/services/batch_service.py

from sqlalchemy import exc
from sqlalchemy.orm import Session

from app.models.batch import Batch  # 假设你的 Batch 模型定义在这里


class BatchService:
    def __init__(self, db_session: Session):
        self.db = db_session

    def create_batch(self, product_id: str, batch_info: dict):
        """
        创建新的批次记录。
        :param product_id: 产品的唯一标识符。
        :param batch_info: 包含批次信息的字典，例如 {'batch_number': 'B123', 'expiry_date': '2026-10-04', 'quantity': 100}。
        :raises exc.SQLAlchemyError: 如果数据库操作失败。
        :return: 创建的 Batch 对象。
        """
        try:
            new_batch = Batch(
                product_id=product_id,
                batch_number=batch_info.get("batch_number"),
                expiry_date=batch_info.get("expiry_date"),
                quantity=batch_info.get("quantity"),
            )
            self.db.add(new_batch)
            self.db.commit()
            self.db.refresh(new_batch)
            return new_batch
        except exc.SQLAlchemyError as e:
            self.db.rollback()
            print(f"创建批次失败: {e}")
            raise e

    def get_batches_by_product(self, product_id: str) -> list[Batch]:
        """
        根据产品ID查询所有相关批次，并按保质期升序排列（先进先出）。
        :param product_id: 产品的唯一标识符。
        :return: 批次对象列表。
        """
        batches = (
            self.db.query(Batch)
            .filter(Batch.product_id == product_id, Batch.quantity > 0)
            .order_by(Batch.expiry_date.asc())
            .all()
        )

        return batches

    def update_batch_quantity(self, batch_id: int, new_quantity: int):
        """
        更新某个批次的库存数量。
        :param batch_id: 批次的唯一标识符。
        :param new_quantity: 新的库存数量。
        :raises ValueError: 如果批次未找到。
        :raises exc.SQLAlchemyError: 如果数据库操作失败。
        """
        try:
            with self.db.begin():
                batch_record = (
                    self.db.query(Batch).filter(Batch.id == batch_id).with_for_update().first()
                )
                if not batch_record:
                    raise ValueError(f"批次ID {batch_id} 未找到。")

                batch_record.quantity = new_quantity

        except (ValueError, exc.SQLAlchemyError) as e:
            self.db.rollback()
            print(f"更新批次数量失败: {e}")
            raise e
