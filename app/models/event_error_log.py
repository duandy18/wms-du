from __future__ import annotations
from sqlalchemy import Column, Integer, String, DateTime, JSON, func
from app.db import Base

class EventErrorLog(Base):
    __tablename__ = "event_error_log"

    id = Column(Integer, primary_key=True)
    platform = Column(String(32), nullable=False)
    event_id = Column(String(64), nullable=True)
    error_type = Column(String(64), nullable=False)
    message = Column(String(255))
    payload = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
