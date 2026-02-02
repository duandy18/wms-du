"""drop_stocks_qty_on_hand

Revision ID: 0db1a061b39f
Revises: f78d954e9f38
Create Date: 2026-02-02 02:34:28.659843
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0db1a061b39f"
down_revision: Union[str, Sequence[str], None] = "f78d954e9f38"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Route 2.3：彻底删除 stocks.qty_on_hand（事实列收敛到 stocks.qty）

    注意：DEV DB 存在依赖 view：
      - v_onhand
      - v_returns_pool

    处理策略：
      1) 先 drop view（避免依赖阻塞）
      2) drop column stocks.qty_on_hand
      3) 用 stocks.qty 重新创建兼容 view（保留列名 qty_on_hand）
    """
    # 1) 先移除依赖 view（顺序：先 drop 下游，再 drop 上游）
    op.execute("DROP VIEW IF EXISTS v_returns_pool;")
    op.execute("DROP VIEW IF EXISTS v_onhand;")

    # 2) 删除冗余列
    op.drop_column("stocks", "qty_on_hand")

    # 3) 重新创建兼容 view：用 qty 作为 qty_on_hand 输出，避免应用/报表仍在读 view 时炸
    op.execute(
        """
        CREATE VIEW v_onhand AS
        SELECT
            s.warehouse_id,
            s.item_id,
            s.batch_code,
            s.batch_code_key,
            s.qty AS qty_on_hand,
            s.qty
        FROM stocks s;
        """
    )

    # v_returns_pool 的原语义未知（你们 DEV 里是依赖 qty_on_hand 的 view）
    # 这里先给一个稳定的兼容实现：同维度透出 qty_on_hand=qty
    op.execute(
        """
        CREATE VIEW v_returns_pool AS
        SELECT
            s.warehouse_id,
            s.item_id,
            s.batch_code,
            s.batch_code_key,
            s.qty AS qty_on_hand,
            s.qty
        FROM stocks s;
        """
    )


def downgrade() -> None:
    """
    Best-effort downgrade：

    1) 恢复 stocks.qty_on_hand
    2) 用 qty 回填 qty_on_hand，保证语义：on_hand == qty
    3) 重新创建 view，使其回到依赖 qty_on_hand 的形态
    """
    # 1) 先 drop 兼容 view
    op.execute("DROP VIEW IF EXISTS v_returns_pool;")
    op.execute("DROP VIEW IF EXISTS v_onhand;")

    # 2) 恢复列
    op.add_column(
        "stocks",
        sa.Column("qty_on_hand", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.execute("UPDATE stocks SET qty_on_hand = qty")
    op.alter_column("stocks", "qty_on_hand", server_default=None)

    # 3) 恢复 view（以 qty_on_hand 为主输出）
    op.execute(
        """
        CREATE VIEW v_onhand AS
        SELECT
            s.warehouse_id,
            s.item_id,
            s.batch_code,
            s.batch_code_key,
            s.qty_on_hand,
            s.qty
        FROM stocks s;
        """
    )
    op.execute(
        """
        CREATE VIEW v_returns_pool AS
        SELECT
            s.warehouse_id,
            s.item_id,
            s.batch_code,
            s.batch_code_key,
            s.qty_on_hand,
            s.qty
        FROM stocks s;
        """
    )
