# alembic/env.py — 屏蔽列注释差异（含定点忽略 batches.expire_at）

from __future__ import annotations

import os
import re
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import create_engine, MetaData
from sqlalchemy.engine import Connection
from sqlalchemy.pool import NullPool

# Alembic 基本配置
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 延迟加载模型（避免导入时机引发的问题）
from app.db.base import Base, init_models  # noqa: E402

# 可选：范围校验开关
CHECK_SCOPE = (os.getenv("ALEMBIC_CHECK_SCOPE") or "all").lower()
PHASE2_TABLES = {
    "orders", "order_items", "order_lines", "order_state_snapshot",
    "reservation_lines", "pick_tasks", "pick_task_lines",
    "outbound_commits", "outbound_ship_ops",
    "platform_events", "event_store", "event_log", "event_error_log",
    "audit_events",
}
PHASE3_TABLES = {"stocks", "batches", "stock_ledger", "snapshots"}
PHASE3_DEPS = {"items", "warehouses"}

def build_scoped_metadata(scope: str) -> MetaData:
    md = MetaData()
    if scope == "all":
        for t in Base.metadata.tables.values():
            t.tometadata(md)
        return md
    wanted: set[str] = set()
    if scope == "phase2":
        wanted |= PHASE2_TABLES
    elif scope == "phase3":
        wanted |= (PHASE3_TABLES | PHASE3_DEPS)
    else:
        for t in Base.metadata.tables.values():
            t.tometadata(md)
        return md
    for name, tbl in Base.metadata.tables.items():
        if name in wanted:
            tbl.tometadata(md)
    return md

# 忽略备份对象
BACKUP_SUFFIX = os.getenv("WMS_BACKUP_SUFFIX", "20251109")
_BACKUP_RE = re.compile(rf".*_{re.escape('backup_' + BACKUP_SUFFIX)}$", re.IGNORECASE)

def include_object(obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any) -> bool:
    """控制 autogenerate 对象筛选。"""
    n = name or ""
    # 1) 忽略备份表/索引/序列
    if type_ in {"table", "index", "sequence"} and _BACKUP_RE.match(n):
        return False
    # 2) 增量策略：不删除 DB 有而模型没有的对象
    if reflected and compare_to is None:
        return False
    # 3) 定点静音：彻底跳过 batches.expire_at（防止 modify_comment 噪音）
    #    - Alembic 对 column 比较时会把列对象作为 obj 传入，name 是列名
    #    - 通过 obj.table.name 判断所属表
    try:
        if type_ == "column" and name == "expire_at" and getattr(obj.table, "name", "") == "batches":
            return False
    except Exception:
        pass
    return True

# 连接串规范化
import re as _re
_DRV_RE = _re.compile(r"\+asyncpg\b|\+psycopg2\b|\+pg8000\b", _re.I)
def normalize_pg_url(url: str) -> str:
    if not url:
        return url
    url = _DRV_RE.sub("+psycopg", url)
    url = _re.sub(r"^postgres://", "postgresql+psycopg://", url, flags=_re.I)
    url = _re.sub(r"^postgresql://", "postgresql+psycopg://", url, flags=_re.I)
    return url

def get_url() -> str:
    url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError("DATABASE_URL 未设置，且 alembic.ini 未提供 sqlalchemy.url")
    return normalize_pg_url(url)

# 生成修订时，额外过滤列注释变更（若你的 Alembic 版本支持 ModifyColumnCommentOp）
try:
    from alembic.operations.ops import ModifyColumnCommentOp  # >=1.11
except Exception:
    ModifyColumnCommentOp = None

def strip_comment_ops(context, revision, directives):
    if not directives or ModifyColumnCommentOp is None:
        return
    script = directives[0]
    if hasattr(script, "upgrade_ops") and script.upgrade_ops:
        script.upgrade_ops.ops = [
            op for op in script.upgrade_ops.ops
            if not isinstance(op, ModifyColumnCommentOp)
        ]
    if hasattr(script, "downgrade_ops") and script.downgrade_ops:
        script.downgrade_ops.ops = [
            op for op in script.downgrade_ops.ops
            if not isinstance(op, ModifyColumnCommentOp)
        ]

def run_migrations_offline() -> None:
    init_models()
    target_metadata = build_scoped_metadata(CHECK_SCOPE)
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=False,
        # 关键：禁用列注释比较
        compare_column_comments=False,
        include_object=include_object,
        process_revision_directives=strip_comment_ops,
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    init_models()
    target_metadata = build_scoped_metadata(CHECK_SCOPE)

    engine = create_engine(get_url(), poolclass=NullPool, future=True)
    db_schema = os.getenv("DB_SCHEMA")  # 多 schema 环境可设置

    with engine.connect() as connection:  # type: Connection
        if db_schema:
            connection.exec_driver_sql(f"SET search_path TO {db_schema}")
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=False,
            # 关键：禁用列注释比较
            compare_column_comments=False,
            include_object=include_object,
            render_as_batch=False,
            version_table_schema=db_schema if db_schema else None,
            include_schemas=bool(db_schema),
            process_revision_directives=strip_comment_ops,
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
