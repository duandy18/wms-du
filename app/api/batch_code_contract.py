# app/api/batch_code_contract.py
"""
DEPRECATED（Phase M-4 governance）：

- 新语义锚点：app.api.lot_code_contract
- 本文件仅作为历史兼容层：保留旧函数名/旧字段名（batch_code）

注意：这里不引入新逻辑，只做别名转发，确保行为不变。
"""

from __future__ import annotations

from typing import Optional

from app.api.lot_code_contract import (
    fetch_item_by_sku as fetch_item_by_sku,
    fetch_item_expiry_policy_map as fetch_item_expiry_policy_map,
    http_422 as http_422,
    normalize_optional_lot_code as normalize_optional_lot_code,
    validate_lot_code_contract as validate_lot_code_contract,
)

# ---- 旧名兼容（对外不破坏）----


def normalize_optional_batch_code(raw: Optional[str]) -> Optional[str]:
    return normalize_optional_lot_code(raw)


def validate_batch_code_contract(*, requires_batch: bool, batch_code: Optional[str]) -> Optional[str]:
    return validate_lot_code_contract(requires_batch=requires_batch, lot_code=batch_code)
