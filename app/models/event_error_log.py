from sqlalchemy import Column, Integer, String, DateTime, JSON, func
from app.db import Base

class EventErrorLog(Base):
    __tablename__ = "event_error_log"

    id = Column(Integer, primary_key=True)
    platform = Column(String(32), nullable=False)
    event_id = Column(String(64), nullable=True)
    error_type = Column(String(64), nullable=False)
    message = Column(String)  # 已在迁移中改为 TEXT
    payload = Column(JSON)
    shop_id = Column(String(64), nullable=True)  # 新增：店铺维度
    created_at = Column(DateTime(timezone=True), server_default=func.now())
