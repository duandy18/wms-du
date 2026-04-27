# Module split: platform order ingestion owns platform order pull job state and run logs.
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PlatformOrderPullJob(Base):
    __tablename__ = "platform_order_pull_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    store_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False)
    job_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="manual")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    time_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    time_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    order_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_size: Mapped[int] = mapped_column(Integer, nullable=False, server_default="50")
    cursor_page: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    request_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    runs: Mapped[list[PlatformOrderPullJobRun]] = relationship(
        "PlatformOrderPullJobRun",
        back_populates="job",
        cascade="all, delete-orphan",
    )


class PlatformOrderPullJobRun(Base):
    __tablename__ = "platform_order_pull_job_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("platform_order_pull_jobs.id", ondelete="CASCADE"), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    store_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="running")
    page: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    page_size: Mapped[int] = mapped_column(Integer, nullable=False, server_default="50")
    has_more: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    orders_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    request_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    job: Mapped[PlatformOrderPullJob] = relationship("PlatformOrderPullJob", back_populates="runs")
    logs: Mapped[list[PlatformOrderPullJobRunLog]] = relationship(
        "PlatformOrderPullJobRunLog",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class PlatformOrderPullJobRunLog(Base):
    __tablename__ = "platform_order_pull_job_run_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("platform_order_pull_jobs.id", ondelete="CASCADE"), nullable=False)
    run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("platform_order_pull_job_runs.id", ondelete="CASCADE"), nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False, server_default="info")
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    platform_order_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    native_order_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    run: Mapped[PlatformOrderPullJobRun] = relationship("PlatformOrderPullJobRun", back_populates="logs")
