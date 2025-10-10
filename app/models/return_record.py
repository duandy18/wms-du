# app/models/return_record.py

from datetime import UTC, datetime  # 导入 UTC

from sqlalchemy import TIMESTAMP, Column, Integer, String

from app.db.base import Base


class ReturnRecord(Base):
    """
    用于记录商品退货详情的数据库模型。
    """

    __tablename__ = "return_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    order_id = Column(String, nullable=False, comment="关联的订单ID")
    product_id = Column(String, nullable=False, comment="退货产品ID")
    quantity = Column(Integer, nullable=False, comment="退货数量")
    reason = Column(String, nullable=True, comment="退货原因")
    # 修复：将默认值改为使用带时区的 UTC 时间
    created_at = Column(TIMESTAMP, default=lambda: datetime.now(UTC))
