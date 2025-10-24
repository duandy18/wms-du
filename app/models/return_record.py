from datetime import UTC, datetime
from sqlalchemy import TIMESTAMP, Column, Integer, String
from app.db.base import Base


class ReturnRecord(Base):
    __tablename__ = "return_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    order_id = Column(String, nullable=False, comment="关联的订单ID")
    product_id = Column(String, nullable=False, comment="退货产品ID")
    quantity = Column(Integer, nullable=False, comment="退货数量")
    reason = Column(String, nullable=True, comment="退货原因")
    created_at = Column(TIMESTAMP(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
