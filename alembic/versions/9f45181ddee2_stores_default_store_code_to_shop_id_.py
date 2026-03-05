"""stores: default store_code to shop_id via trigger

Revision ID: 9f45181ddee2
Revises: 57956027eeec
Create Date: 2026-02-09 19:42:21.855651

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9f45181ddee2"
down_revision: Union[str, Sequence[str], None] = "57956027eeec"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    保证 stores.store_code 在 INSERT 时永不为 NULL：

    - 兼容历史与测试代码：允许只插 platform / shop_id / name
    - 事实规则：若未显式提供 store_code，则默认使用 shop_id
    """

    # 1) 防御性回填：历史数据中若存在 NULL / 空字符串，统一回填为 shop_id
    op.execute(
        """
        UPDATE stores
           SET store_code = shop_id
         WHERE store_code IS NULL OR btrim(store_code) = ''
        """
    )

    # 2) 创建 / 更新触发器函数
    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_stores_store_code_default()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF NEW.store_code IS NULL OR btrim(NEW.store_code) = '' THEN
            NEW.store_code := NEW.shop_id;
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )

    # 3) 创建 BEFORE INSERT 触发器（只兜 INSERT，不干扰 UPDATE 语义）
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_stores_store_code_default ON stores;
        CREATE TRIGGER trg_stores_store_code_default
        BEFORE INSERT ON stores
        FOR EACH ROW
        EXECUTE FUNCTION trg_stores_store_code_default();
        """
    )


def downgrade() -> None:
    """
    回滚仅移除 trigger 与 function，不回退已写入的数据
    """
    op.execute("DROP TRIGGER IF EXISTS trg_stores_store_code_default ON stores;")
    op.execute("DROP FUNCTION IF EXISTS trg_stores_store_code_default();")
