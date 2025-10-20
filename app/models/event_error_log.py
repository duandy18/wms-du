from sqlalchemy import JSON, Column, DateTime, Integer, String, func

from app.db import Base


class EventErrorLog(Base):
    """记录平台事件处理中的异常信息。"""

    __tablename__ = "event_error_log"

    id = Column(Integer, primary_key=True)
    platform = Column(String(32), nullable=False)
    event_id = Column(String(64), nullable=True)
    error_type = Column(String(64), nullable=False)
    message = Column(String(255))
    payload = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
