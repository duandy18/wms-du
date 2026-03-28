"""adjust_store_platform_access_tables

Revision ID: 2b0d9a228fe4
Revises: 23a116913711
Create Date: 2026-03-28 13:54:09.215877

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2b0d9a228fe4"
down_revision: Union[str, Sequence[str], None] = "23a116913711"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TRIGGER_FUNCTION_NAME = "set_updated_at_timestamp"


def upgrade() -> None:
    """Upgrade schema."""
    # 1) raw_payload_json: json -> jsonb
    op.execute(
        """
        ALTER TABLE store_platform_credentials
        ALTER COLUMN raw_payload_json
        TYPE jsonb
        USING raw_payload_json::jsonb
        """
    )
    op.execute(
        """
        ALTER TABLE store_platform_credentials
        ALTER COLUMN raw_payload_json
        SET DEFAULT '{}'::jsonb
        """
    )

    # 2) 通用 updated_at 触发器函数
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {TRIGGER_FUNCTION_NAME}()
        RETURNS trigger AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )

    # 3) store_platform_credentials 绑定触发器
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_store_platform_credentials_set_updated_at
        ON store_platform_credentials
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER trg_store_platform_credentials_set_updated_at
        BEFORE UPDATE ON store_platform_credentials
        FOR EACH ROW
        EXECUTE FUNCTION {TRIGGER_FUNCTION_NAME}()
        """
    )

    # 4) store_platform_connections 绑定触发器
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_store_platform_connections_set_updated_at
        ON store_platform_connections
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER trg_store_platform_connections_set_updated_at
        BEFORE UPDATE ON store_platform_connections
        FOR EACH ROW
        EXECUTE FUNCTION {TRIGGER_FUNCTION_NAME}()
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_store_platform_connections_set_updated_at
        ON store_platform_connections
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_store_platform_credentials_set_updated_at
        ON store_platform_credentials
        """
    )

    op.execute(
        """
        ALTER TABLE store_platform_credentials
        ALTER COLUMN raw_payload_json
        TYPE json
        USING raw_payload_json::json
        """
    )
    op.execute(
        """
        ALTER TABLE store_platform_credentials
        ALTER COLUMN raw_payload_json
        SET DEFAULT '{}'::json
        """
    )

    op.execute(
        f"DROP FUNCTION IF EXISTS {TRIGGER_FUNCTION_NAME}()"
    )
