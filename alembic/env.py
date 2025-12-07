# alembic/env.py — 屏蔽列注释差异（含定点忽略 batches.expire_at）

from __future__ import annotations

import os
import re
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Connection
from sqlalchemy.pool import NullPool

# Alembic 基本配置
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 延迟加载模型（避免导入时机引发的问题）
from app.db.base import Base, init_models  # noqa: E402

# ---------------------------------------------------------------------------
# 范围控制：按 scope 限定参与 compare 的表集合
# ---------------------------------------------------------------------------

CHECK_SCOPE = (os.getenv("ALEMBIC_CHECK_SCOPE") or "all").lower()

PHASE2_TABLES = {
    "orders",
    "order_items",
    "order_lines",
    "order_state_snapshot",
    "reservation_lines",
    "pick_tasks",
    "pick_task_lines",
    "outbound_commits",
    "outbound_ship_ops",
    "platform_events",
    "event_store",
    "event_log",
    "event_error_log",
    "audit_events",
}

PHASE3_TABLES = {"stocks", "batches", "stock_ledger", "snapshots"}
PHASE3_DEPS = {"items", "warehouses"}


def build_scoped_metadata(scope: str) -> MetaData:
    """
    按 scope 构建一个缩小版的 MetaData，减少 alembic check 的噪音。
    """
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
        # 未知 scope 时退回全量，宁可多查，不搞黑盒
        for t in Base.metadata.tables.values():
            t.tometadata(md)
        return md

    for name, tbl in Base.metadata.tables.items():
        if name in wanted:
            tbl.tometadata(md)

    return md


# ---------------------------------------------------------------------------
# include_object：过滤备份表 / 备份索引 / 备份序列 + 定点静音 batches.expire_at
# ---------------------------------------------------------------------------

BACKUP_SUFFIX = os.getenv("WMS_BACKUP_SUFFIX", "20251109")
_BACKUP_RE = re.compile(rf".*_{re.escape('backup_' + BACKUP_SUFFIX)}$", re.IGNORECASE)


def include_object(
    obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any
) -> bool:
    """
    控制 autogenerate / check 时哪些对象参与 diff。

    规则：
      1) 忽略 *_backup_20251109 之类的备份对象（表 / 索引 / 序列）；
      2) DB 有而模型里没有的对象不参与比较（不自动生成 drop）；
      3) 定点静音 batches.expire_at（避免 comment 差异反复骚扰）。
    """
    n = name or ""

    # 1) 忽略备份表/索引/序列
    if type_ in {"table", "index", "sequence"} and _BACKUP_RE.match(n):
        return False

    # 2) DB 里多出来的对象（reflected=True 且 compare_to=None）不参与 diff，避免莫名其妙的 drop
    if reflected and compare_to is None:
        return False

    # 3) 定点静音 batches.expire_at
    try:
        if (
            type_ == "column"
            and name == "expire_at"
            and getattr(obj.table, "name", "") == "batches"
        ):
            return False
    except Exception:
        # 极端情况下 obj.table 不存在，直接放行
        pass

    return True


# ---------------------------------------------------------------------------
# URL 规范化 + 获取：优先用 WMS_TEST_DATABASE_URL / WMS_DATABASE_URL
# ---------------------------------------------------------------------------

import re as _re

_DRV_RE = _re.compile(r"\+asyncpg\b|\+psycopg2\b|\+pg8000\b", _re.I)


def normalize_pg_url(url: str) -> str:
    if not url:
        return url

    # 统一 driver 前缀为 +psycopg
    url = _DRV_RE.sub("+psycopg", url)
    url = _re.sub(r"^postgres://", "postgresql+psycopg://", url, flags=_re.I)
    # 如果是 postgresql:// 且没指定 driver，也统一成 psycopg
    if url.lower().startswith("postgresql://") and "+psycopg" not in url.lower():
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)

    return url


def get_url() -> str:
    """
    单一真相：显式使用环境变量里的 DSN，不再瞎猜。

    优先级：
      1. WMS_TEST_DATABASE_URL
      2. WMS_DATABASE_URL
      3. DATABASE_URL
      4. alembic.ini 里的 sqlalchemy.url
    """
    url = (
        os.getenv("WMS_TEST_DATABASE_URL")
        or os.getenv("WMS_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or config.get_main_option("sqlalchemy.url")
    )

    if not url:
        raise RuntimeError(
            "Alembic 无法确定数据库 URL：\n"
            "请设置 WMS_TEST_DATABASE_URL / WMS_DATABASE_URL / DATABASE_URL，"
            "或在 alembic.ini 里配置 sqlalchemy.url"
        )

    # 去掉外层意外加上的引号，比如 '"postgresql+psycopg://.../postgres"'
    url = url.strip()
    if (url.startswith('"') and url.endswith('"')) or (
        url.startswith("'") and url.endswith("'")
    ):
        url = url[1:-1].strip()

    return normalize_pg_url(url)


# ---------------------------------------------------------------------------
# 过滤列注释变更（如果 alembic 支持 ModifyColumnCommentOp）
# ---------------------------------------------------------------------------

try:
    from alembic.operations.ops import ModifyColumnCommentOp  # type: ignore[attr-defined]
except Exception:  # 老版本 Alembic 没这个类型
    ModifyColumnCommentOp = None


def strip_comment_ops(context, revision, directives):
    """
    在 autogenerate/revision 时，静音所有 ModifyColumnCommentOp，
    避免 column comment 的噪音（尤其是 triggers/工具自动改 comment 时）。
    """
    if not directives or ModifyColumnCommentOp is None:
        return

    script = directives[0]

    if hasattr(script, "upgrade_ops") and script.upgrade_ops:
        script.upgrade_ops.ops = [
            op for op in script.upgrade_ops.ops if not isinstance(op, ModifyColumnCommentOp)
        ]

    if hasattr(script, "downgrade_ops") and script.downgrade_ops:
        script.downgrade_ops.ops = [
            op for op in script.downgrade_ops.ops if not isinstance(op, ModifyColumnCommentOp)
        ]


# ---------------------------------------------------------------------------
# 迁移执行函数
# ---------------------------------------------------------------------------


def run_migrations_offline() -> None:
    """
    Offline 模式：不真实连库，只生成 SQL。
    """
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
        compare_column_comments=False,  # 关键：禁用列注释比较
        include_object=include_object,
        process_revision_directives=strip_comment_ops,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Online 模式：真实连库执行迁移。
    """
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
            compare_column_comments=False,  # 关键：禁用列注释比较
            include_object=include_object,
            render_as_batch=False,
            version_table_schema=db_schema if db_schema else None,
            include_schemas=bool(db_schema),
            process_revision_directives=strip_comment_ops,
        )

        with context.begin_transaction():
            context.run_migrations()


# ---------------------------------------------------------------------------
# 入口：根据 offline/online 模式选择执行路径
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
