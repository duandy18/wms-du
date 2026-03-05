"""stock_ledger_idem_unique_add_scope

Revision ID: 2d119fb173a7
Revises: 8615b1c6bffb
Create Date: 2026-02-13 14:16:52.944084

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2d119fb173a7"
down_revision: Union[str, Sequence[str], None] = "8615b1c6bffb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Phase Scope 双账本之后的幂等唯一升级：

    原合同：
      (warehouse_id, batch_code_key, item_id, reason, ref, ref_line)

    新合同（必须纳入 scope，避免 DRILL / PROD 串账）：
      (scope, warehouse_id, batch_code_key, item_id, reason, ref, ref_line)
    """

    # 1️⃣ 尝试删除旧的“无 scope”的幂等唯一索引（如果存在）
    # 旧名字不确定，因此用 IF EXISTS + 常见命名兜底
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                  FROM pg_indexes
                 WHERE tablename = 'stock_ledger'
                   AND indexname = 'uq_stock_ledger_idem'
            ) THEN
                EXECUTE 'DROP INDEX uq_stock_ledger_idem';
            END IF;
        END
        $$;
        """
    )

    # 2️⃣ 创建新的 scope-aware 幂等唯一索引
    op.create_index(
        "uq_stock_ledger_idem_v2_scope",
        "stock_ledger",
        [
            "scope",
            "warehouse_id",
            "batch_code_key",
            "item_id",
            "reason",
            "ref",
            "ref_line",
        ],
        unique=True,
    )


def downgrade() -> None:
    # 删除 v2 索引
    op.drop_index("uq_stock_ledger_idem_v2_scope", table_name="stock_ledger")

    # 可选：回退旧结构（不自动重建旧索引，避免误回退历史结构）
    # 如需完全回退，请自行添加旧索引定义。
