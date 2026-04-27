"""platform order pull jobs

Revision ID: 9b8c7d6e5f4a
Revises: c3a7f8e49b20
Create Date: 2026-04-27
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "9b8c7d6e5f4a"
down_revision: Union[str, Sequence[str], None] = "c3a7f8e49b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_JOB_STATUSES = ("pending", "running", "success", "partial_success", "failed", "cancelled")
_RUN_STATUSES = ("running", "success", "partial_success", "failed")
_JOB_TYPES = ("manual", "scheduled", "repair")
_PLATFORMS = ("pdd", "taobao", "jd")
_LOG_LEVELS = ("info", "warn", "error")


def upgrade() -> None:
    op.create_table(
        "platform_order_pull_jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("store_id", sa.BigInteger(), nullable=False),
        sa.Column("job_type", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("time_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("time_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("order_status", sa.Integer(), nullable=True),
        sa.Column("page_size", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("cursor_page", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("request_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_platform_order_pull_jobs_store_id", ondelete="RESTRICT"),
        sa.CheckConstraint(f"platform in {repr(_PLATFORMS)}", name="ck_platform_order_pull_jobs_platform"),
        sa.CheckConstraint(f"job_type in {repr(_JOB_TYPES)}", name="ck_platform_order_pull_jobs_job_type"),
        sa.CheckConstraint(f"status in {repr(_JOB_STATUSES)}", name="ck_platform_order_pull_jobs_status"),
        sa.CheckConstraint("page_size > 0 AND page_size <= 100", name="ck_platform_order_pull_jobs_page_size"),
        sa.CheckConstraint("cursor_page > 0", name="ck_platform_order_pull_jobs_cursor_page"),
    )
    op.create_index("ix_platform_order_pull_jobs_platform", "platform_order_pull_jobs", ["platform"])
    op.create_index("ix_platform_order_pull_jobs_store_id", "platform_order_pull_jobs", ["store_id"])
    op.create_index("ix_platform_order_pull_jobs_status", "platform_order_pull_jobs", ["status"])
    op.create_index("ix_platform_order_pull_jobs_created_at", "platform_order_pull_jobs", ["created_at"])

    op.create_table(
        "platform_order_pull_job_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.BigInteger(), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("store_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("page", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("page_size", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("has_more", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("orders_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("request_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["job_id"], ["platform_order_pull_jobs.id"], name="fk_platform_order_pull_job_runs_job_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_platform_order_pull_job_runs_store_id", ondelete="RESTRICT"),
        sa.CheckConstraint(f"platform in {repr(_PLATFORMS)}", name="ck_platform_order_pull_job_runs_platform"),
        sa.CheckConstraint(f"status in {repr(_RUN_STATUSES)}", name="ck_platform_order_pull_job_runs_status"),
        sa.CheckConstraint("page > 0", name="ck_platform_order_pull_job_runs_page"),
        sa.CheckConstraint("page_size > 0 AND page_size <= 100", name="ck_platform_order_pull_job_runs_page_size"),
        sa.CheckConstraint("orders_count >= 0 AND success_count >= 0 AND failed_count >= 0", name="ck_platform_order_pull_job_runs_counts"),
    )
    op.create_index("ix_platform_order_pull_job_runs_job_id", "platform_order_pull_job_runs", ["job_id"])
    op.create_index("ix_platform_order_pull_job_runs_platform", "platform_order_pull_job_runs", ["platform"])
    op.create_index("ix_platform_order_pull_job_runs_store_id", "platform_order_pull_job_runs", ["store_id"])
    op.create_index("ix_platform_order_pull_job_runs_status", "platform_order_pull_job_runs", ["status"])
    op.create_index("ix_platform_order_pull_job_runs_started_at", "platform_order_pull_job_runs", ["started_at"])

    op.create_table(
        "platform_order_pull_job_run_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.BigInteger(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("platform_order_no", sa.String(length=128), nullable=True),
        sa.Column("native_order_id", sa.BigInteger(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["job_id"], ["platform_order_pull_jobs.id"], name="fk_platform_order_pull_job_run_logs_job_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["platform_order_pull_job_runs.id"], name="fk_platform_order_pull_job_run_logs_run_id", ondelete="CASCADE"),
        sa.CheckConstraint(f"level in {repr(_LOG_LEVELS)}", name="ck_platform_order_pull_job_run_logs_level"),
    )
    op.create_index("ix_platform_order_pull_job_run_logs_job_id", "platform_order_pull_job_run_logs", ["job_id"])
    op.create_index("ix_platform_order_pull_job_run_logs_run_id", "platform_order_pull_job_run_logs", ["run_id"])
    op.create_index("ix_platform_order_pull_job_run_logs_event_type", "platform_order_pull_job_run_logs", ["event_type"])
    op.create_index("ix_platform_order_pull_job_run_logs_created_at", "platform_order_pull_job_run_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_platform_order_pull_job_run_logs_created_at", table_name="platform_order_pull_job_run_logs")
    op.drop_index("ix_platform_order_pull_job_run_logs_event_type", table_name="platform_order_pull_job_run_logs")
    op.drop_index("ix_platform_order_pull_job_run_logs_run_id", table_name="platform_order_pull_job_run_logs")
    op.drop_index("ix_platform_order_pull_job_run_logs_job_id", table_name="platform_order_pull_job_run_logs")
    op.drop_table("platform_order_pull_job_run_logs")

    op.drop_index("ix_platform_order_pull_job_runs_started_at", table_name="platform_order_pull_job_runs")
    op.drop_index("ix_platform_order_pull_job_runs_status", table_name="platform_order_pull_job_runs")
    op.drop_index("ix_platform_order_pull_job_runs_store_id", table_name="platform_order_pull_job_runs")
    op.drop_index("ix_platform_order_pull_job_runs_platform", table_name="platform_order_pull_job_runs")
    op.drop_index("ix_platform_order_pull_job_runs_job_id", table_name="platform_order_pull_job_runs")
    op.drop_table("platform_order_pull_job_runs")

    op.drop_index("ix_platform_order_pull_jobs_created_at", table_name="platform_order_pull_jobs")
    op.drop_index("ix_platform_order_pull_jobs_status", table_name="platform_order_pull_jobs")
    op.drop_index("ix_platform_order_pull_jobs_store_id", table_name="platform_order_pull_jobs")
    op.drop_index("ix_platform_order_pull_jobs_platform", table_name="platform_order_pull_jobs")
    op.drop_table("platform_order_pull_jobs")
