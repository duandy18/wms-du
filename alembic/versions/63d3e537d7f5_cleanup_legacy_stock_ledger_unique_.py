"""cleanup legacy stock/ledger unique constraints

Revision ID: 63d3e537d7f5
Revises: 3a5761b8cbd5
Create Date: 2026-02-01 21:01:19.399827

本迁移的唯一目的（严格单主线）：
- 清理依赖 batch_code 的旧唯一约束 / 旧幂等约束
- 清理过于粗暴的 (reason, ref, ref_line) 全局唯一约束
- 让系统只剩下以 batch_code_key 为核心的“正确唯一性/幂等性”

不做的事情：
- 不做历史数据修复（NOEXP → NULL）
- 不改任何业务代码
- 不新增任何新约束
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "63d3e537d7f5"
down_revision: Union[str, Sequence[str], None] = "3a5761b8cbd5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # stocks：移除 legacy 唯一约束 (warehouse_id, item_id, batch_code)
    # ------------------------------------------------------------------
    # 正确约束已经是：
    #   uq_stocks_item_wh_batch (item_id, warehouse_id, batch_code_key)
    # legacy 的 uq_stocks_wh_item_code 只会制造歧义
    op.drop_constraint(
        "uq_stocks_wh_item_code",
        "stocks",
        type_="unique",
    )

    # 某些历史版本可能还伴随一个同名索引，安全起见尝试清理
    try:
        op.drop_index("ix_stocks_wh_item_code", table_name="stocks")
    except Exception:
        pass

    # ------------------------------------------------------------------
    # stock_ledger：移除 legacy 幂等约束（依赖 batch_code）
    # ------------------------------------------------------------------
    # 正确幂等已经是：
    #   uq_ledger_wh_batch_item_reason_ref_line (… batch_code_key …)
    op.drop_constraint(
        "uq_ledger_idem_reason_refline_item_code_wh",
        "stock_ledger",
        type_="unique",
    )

    # ------------------------------------------------------------------
    # stock_ledger：移除过于粗暴的全局唯一约束
    # (reason, ref, ref_line)
    # ------------------------------------------------------------------
    # 这些约束会禁止：
    # - 同一订单 ref / ref_line 下出现多 item
    # - 同一 ref 下出现多批次/多仓的合理台账
    # 已完全被更精确的 batch_code_key 幂等约束取代
    op.drop_constraint(
        "uq_ledger_reason_ref_refline",
        "stock_ledger",
        type_="unique",
    )
    op.drop_constraint(
        "uq_stock_ledger_reason_ref_refline",
        "stock_ledger",
        type_="unique",
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # stock_ledger：恢复过于粗暴的全局唯一约束
    # ------------------------------------------------------------------
    op.create_unique_constraint(
        "uq_stock_ledger_reason_ref_refline",
        "stock_ledger",
        ["reason", "ref", "ref_line"],
    )
    op.create_unique_constraint(
        "uq_ledger_reason_ref_refline",
        "stock_ledger",
        ["reason", "ref", "ref_line"],
    )

    # ------------------------------------------------------------------
    # stock_ledger：恢复 legacy 幂等约束（依赖 batch_code）
    # ------------------------------------------------------------------
    op.create_unique_constraint(
        "uq_ledger_idem_reason_refline_item_code_wh",
        "stock_ledger",
        ["reason", "ref", "ref_line", "item_id", "batch_code", "warehouse_id"],
    )

    # ------------------------------------------------------------------
    # stocks：恢复 legacy 唯一约束 (warehouse_id, item_id, batch_code)
    # ------------------------------------------------------------------
    op.create_unique_constraint(
        "uq_stocks_wh_item_code",
        "stocks",
        ["warehouse_id", "item_id", "batch_code"],
    )

    # 对应索引是否存在取决于历史版本，谨慎起见尝试恢复
    try:
        op.create_index(
            "ix_stocks_wh_item_code",
            "stocks",
            ["warehouse_id", "item_id", "batch_code"],
            unique=False,
        )
    except Exception:
        pass
