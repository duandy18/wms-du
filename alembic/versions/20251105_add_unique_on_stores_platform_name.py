"""add unique constraint on stores(platform, name) for outbound ON CONFLICT

Revision ID: 20251105_add_unique_on_stores_platform_name
Revises: 3e4f41e0de8d
Create Date: 2025-11-05 00:00:00
"""

from __future__ import annotations

from typing import Optional, Sequence

from alembic import op
import sqlalchemy as sa

# ---- ids ----
revision: str = "20251105_add_unique_on_stores_platform_name"
down_revision: Optional[str] = "3e4f41e0de8d"
branch_labels: Optional[Sequence[str]] = None
depends_on: Optional[Sequence[str]] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 0) 预检查：若已经有唯一约束/索引，直接补齐另一项后返回
    uqs = {
        uc["name"]: set(uc.get("column_names") or [])
        for uc in insp.get_unique_constraints("stores")
    }
    idx_names = {ix["name"] for ix in insp.get_indexes("stores")}
    has_unique = any(cols == {"platform", "name"} for cols in uqs.values()) or (
        "uq_stores_platform_name_idx" in idx_names
    )

    # 1) 先合并重复：保留每组 MIN(id) 作为 keep_id，把所有子表引用指向 keep_id，再删掉 dup_ids
    #    - 本段对不存在的表/列采用 TRY-UPDATE 方案（若表不存在或无该列则忽略）
    #    - 需要子表上的 FK 为标准命名，不然作为普通 UPDATE 也没问题
    with op.get_context().autocommit_block():
        # 1.1 聚合重复
        op.execute(
            sa.text("""
            CREATE TEMP TABLE __stores_dups AS
            SELECT platform, name,
                   MIN(id)                                  AS keep_id,
                   ARRAY_REMOVE(ARRAY_AGG(id), MIN(id))     AS dup_ids
            FROM stores
            GROUP BY platform, name
            HAVING COUNT(*) > 1;
        """)
        )

        # 1.2 若无重复，直接跳过后续清理
        res = bind.execute(sa.text("SELECT COUNT(*) FROM __stores_dups")).scalar()
        if res and int(res) > 0:
            # 子表枚举：按你工程常见外键表处理；不存在则忽略
            for table in ("store_items", "channel_inventory", "outbound_ship_ops"):
                # 检查表是否存在 & 是否包含 store_id 列
                if table in insp.get_table_names(schema="public"):
                    cols = {c["name"] for c in insp.get_columns(table)}
                    if "store_id" in cols:
                        op.execute(
                            sa.text(f"""
                            UPDATE {table} t
                               SET store_id = d.keep_id
                              FROM __stores_dups d
                             WHERE t.store_id = ANY(d.dup_ids)
                        """)
                        )

            # 1.3 删除重复的 stores 行
            op.execute(
                sa.text("""
                DELETE FROM stores s
                 USING __stores_dups d
                 WHERE s.id = ANY(d.dup_ids);
            """)
            )

        # 1.4 清理临时表
        op.execute(sa.text("DROP TABLE IF EXISTS __stores_dups"))

    # 2) 创建唯一索引 + 约束（若不存在）
    if "uq_stores_platform_name_idx" not in idx_names:
        op.execute(
            sa.text("CREATE UNIQUE INDEX uq_stores_platform_name_idx ON stores(platform, name)")
        )

    # 有些环境只有唯一索引，没有命名唯一约束；此处把索引挂成约束（若约束还没有）
    uqs_after = {
        uc["name"]: set(uc.get("column_names") or [])
        for uc in insp.get_unique_constraints("stores")
    }
    if not any(cols == {"platform", "name"} for cols in uqs_after.values()):
        # 只有 PG 支持 "USING INDEX" 语法；这里假定后端为 PG（你的工程就是）
        op.execute(
            sa.text(
                "ALTER TABLE stores ADD CONSTRAINT uq_stores_platform_name UNIQUE USING INDEX uq_stores_platform_name_idx"
            )
        )

    # 3) 顺手补一个常用查询索引（平台+激活态）
    idx_names = {ix["name"] for ix in insp.get_indexes("stores")}
    if "ix_stores_platform_active" not in idx_names:
        op.create_index("ix_stores_platform_active", "stores", ["platform", "active"])


def downgrade() -> None:
    # 回滚只移除约束与索引；被合并的重复行无法自动还原
    bind = op.get_bind()
    insp = sa.inspect(bind)

    uqs = {
        uc["name"]: set(uc.get("column_names") or [])
        for uc in insp.get_unique_constraints("stores")
    }
    if "uq_stores_platform_name" in uqs:
        op.drop_constraint("uq_stores_platform_name", "stores", type_="unique")

    idx_names = {ix["name"] for ix in insp.get_indexes("stores")}
    if "uq_stores_platform_name_idx" in idx_names:
        op.drop_index("uq_stores_platform_name_idx", table_name="stores")
    if "ix_stores_platform_active" in idx_names:
        op.drop_index("ix_stores_platform_active", table_name="stores")
