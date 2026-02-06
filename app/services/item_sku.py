# app/services/item_sku.py
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

SKU_SEQ_NAME = "items_sku_seq"
SKU_PREFIX = "AKT-"
SKU_PAD_WIDTH = 6


def next_sku(db: Session) -> str:
    """
    SKU 后端权威发号（并发安全）：
    - AKT-000001...
    - 依赖 DB sequence items_sku_seq（由 Alembic migration 创建）
    """
    try:
        n = db.execute(text(f"SELECT nextval('{SKU_SEQ_NAME}')")).scalar_one()
    except Exception as e:
        # 给一个更可定位的错误（新环境漏跑迁移时一眼看懂）
        raise RuntimeError(
            f"SKU sequence missing or unavailable: {SKU_SEQ_NAME}. "
            "Please run alembic upgrade head."
        ) from e

    num = str(int(n)).zfill(SKU_PAD_WIDTH)
    return f"{SKU_PREFIX}{num}"
