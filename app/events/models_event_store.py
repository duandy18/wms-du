from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, declarative_base, mapped_column

Base = declarative_base()


class EventRow(Base):
    __tablename__ = "event_store"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime]
    topic: Mapped[str] = mapped_column(String(64))
    key: Mapped[str | None] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSON)
    headers: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str | None] = mapped_column(String(64))
    checksum: Mapped[str | None] = mapped_column(String(64))
