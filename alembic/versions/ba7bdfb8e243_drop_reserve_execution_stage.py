"""drop_reserve_execution_stage

Revision ID: ba7bdfb8e243
Revises: c7d43049ddd6
Create Date: 2026-02-26

Phase 5：
- 数据清洗：execution_stage = 'RESERVE' -> 'PICK'
- 约束收紧：只允许 NULL / PICK / SHIP
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ba7bdfb8e243"
down_revision: Union[str, Sequence[str], None] = "c7d43049ddd6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --------------------------------------------------
    # 1) 数据清洗：彻底消灭 RESERVE
    # --------------------------------------------------
    op.execute(
        """
        UPDATE order_fulfillment
           SET execution_stage = 'PICK'
         WHERE execution_stage = 'RESERVE'
        """
    )

    # --------------------------------------------------
    # 2) 收紧 CHECK 约束：不再允许 RESERVE
    # --------------------------------------------------
    op.drop_constraint(
        "ck_order_fulfillment_execution_stage",
        "order_fulfillment",
        type_="check",
    )

    op.create_check_constraint(
        "ck_order_fulfillment_execution_stage",
        "order_fulfillment",
        "execution_stage IS NULL OR execution_stage IN ('PICK','SHIP')",
    )


def downgrade() -> None:
    # 不恢复 RESERVE，只恢复旧宽松约束
    op.drop_constraint(
        "ck_order_fulfillment_execution_stage",
        "order_fulfillment",
        type_="check",
    )

    op.create_check_constraint(
        "ck_order_fulfillment_execution_stage",
        "order_fulfillment",
        "execution_stage IS NULL OR execution_stage IN ('PICK','SHIP')",
    )
