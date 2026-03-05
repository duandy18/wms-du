"""guard: forbid retire fsku when referenced by merchant_code bindings

Revision ID: 8fb963d25b29
Revises: 92974195e7fc
Create Date: 2026-02-11 11:50:52.314511
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "8fb963d25b29"
down_revision: Union[str, Sequence[str], None] = "92974195e7fc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # ============================
    # PostgreSQL 版本
    # ============================
    if dialect == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION ck_fskus_retire_not_referenced()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
              -- 仅拦截：从非 retired -> retired 的状态迁移
              IF NEW.status = 'retired'
                 AND (OLD.status IS DISTINCT FROM 'retired') THEN

                IF EXISTS (
                  SELECT 1
                    FROM merchant_code_fsku_bindings b
                   WHERE b.fsku_id = NEW.id
                   LIMIT 1
                ) THEN
                  RAISE EXCEPTION
                    'FSKU % is referenced by merchant_code_fsku_bindings; cannot retire',
                    NEW.id
                    USING ERRCODE = '23514'; -- check_violation
                END IF;

              END IF;

              RETURN NEW;
            END;
            $$;
            """
        )

        op.execute(
            "DROP TRIGGER IF EXISTS trg_ck_fskus_retire_not_referenced ON fskus;"
        )

        op.execute(
            """
            CREATE TRIGGER trg_ck_fskus_retire_not_referenced
            BEFORE UPDATE OF status ON fskus
            FOR EACH ROW
            EXECUTE FUNCTION ck_fskus_retire_not_referenced();
            """
        )
        return

    # ============================
    # SQLite（测试环境）
    # ============================
    if dialect == "sqlite":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_ck_fskus_retire_not_referenced;"
        )

        op.execute(
            """
            CREATE TRIGGER trg_ck_fskus_retire_not_referenced
            BEFORE UPDATE OF status ON fskus
            FOR EACH ROW
            WHEN NEW.status = 'retired'
                 AND (OLD.status IS NULL OR OLD.status <> 'retired')
            BEGIN
              SELECT CASE
                WHEN EXISTS (
                  SELECT 1
                    FROM merchant_code_fsku_bindings b
                   WHERE b.fsku_id = NEW.id
                   LIMIT 1
                )
                THEN RAISE(ABORT,
                  'FSKU is referenced by merchant_code_fsku_bindings; cannot retire')
              END;
            END;
            """
        )
        return

    # 其它数据库方言暂不处理（当前仅 pg + sqlite）


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_ck_fskus_retire_not_referenced ON fskus;"
        )
        op.execute(
            "DROP FUNCTION IF EXISTS ck_fskus_retire_not_referenced();"
        )
        return

    if dialect == "sqlite":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_ck_fskus_retire_not_referenced;"
        )
        return
