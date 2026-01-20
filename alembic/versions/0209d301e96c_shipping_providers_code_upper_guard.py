"""shipping_providers_code_upper_guard

Revision ID: 0209d301e96c
Revises: 2e7e9afa8434
Create Date: 2026-01-20 15:46:31.411270

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0209d301e96c"
down_revision: Union[str, Sequence[str], None] = "2e7e9afa8434"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Phase 1.5：ShippingProvider.code 口径护栏（DB 级）
    #
    # 规则：
    # - code 要么为 NULL
    # - 要么等于 upper(code)
    #
    # 顺序非常重要：
    # 1) 先修历史数据（否则直接加 CHECK 会失败）
    # 2) 再加 CHECK 约束，防止后续回潮
    # ------------------------------------------------------------------

    # 1) 历史数据统一大写（幂等、安全）
    op.execute(
        "UPDATE shipping_providers "
        "SET code = upper(code) "
        "WHERE code IS NOT NULL;"
    )

    # 2) 加 CHECK 约束：code 必须为 NULL 或全大写
    op.create_check_constraint(
        "ck_shipping_providers_code_upper",
        "shipping_providers",
        "code IS NULL OR code = upper(code)",
    )


def downgrade() -> None:
    # 回滚时只移除 CHECK（不反向 lower 数据，避免制造新脏数据）
    op.drop_constraint(
        "ck_shipping_providers_code_upper",
        "shipping_providers",
        type_="check",
    )
