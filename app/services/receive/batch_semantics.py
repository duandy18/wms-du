# app/services/receive/batch_semantics.py
from __future__ import annotations

from typing import Literal, Optional

# 标签来源策略（去耦合后的“标签层”）
# - SUPPLIER：lot_code 必填
# - INTERNAL：lot_code 可空
LotCodeSource = Literal["SUPPLIER", "INTERNAL"]

# Phase L/M：
# - “无批次标签”用 lot_code=None 表达，不鼓励/不接受 NULL_BATCH token 作为业务输入。
# - 禁止 NOEXP/NONE 这种人为伪码作为批次标签。
_PSEUDO_LOT_CODE_TOKENS = {
    "NOEXP",
    "NONE",
}


def normalize_lot_code(lot_code: Optional[str]) -> Optional[str]:
    if lot_code is None:
        return None
    s = str(lot_code).strip()
    return s or None


def is_pseudo_lot_code(lot_code: Optional[str]) -> bool:
    s = normalize_lot_code(lot_code)
    if s is None:
        return False
    return s.upper() in _PSEUDO_LOT_CODE_TOKENS


def parse_lot_code_source_policy(raw: Optional[str]) -> LotCodeSource:
    """
    将 items.lot_source_policy 的值归一到 LotCodeSource。

    约定：
    - enum 名称不猜死：只要包含/前缀为 SUPPLIER 即视为 SUPPLIER 模式
    - 否则默认为 INTERNAL
    """
    s = (raw or "").strip().upper()
    if s.startswith("SUPPLIER") or s == "SUPPLIER":
        return "SUPPLIER"
    return "INTERNAL"


def enforce_lot_code_semantics(*, lot_code_source: LotCodeSource, lot_code: Optional[str]) -> Optional[str]:
    """
    标签层门禁（与有效期日期彻底去耦合）：

    - SUPPLIER：
        - lot_code 必填
        - 禁止伪码（NOEXP/NONE）
    - INTERNAL：
        - lot_code 可空（允许 None）
        - 若提供了 lot_code，也仍然做“伪码禁止”（防止污染）
    """
    code = normalize_lot_code(lot_code)

    if code is not None and is_pseudo_lot_code(code):
        raise ValueError(f"lot_code 禁止伪码 {code!r}")

    if lot_code_source == "SUPPLIER" and code is None:
        raise ValueError("lot_code_source=SUPPLIER：必须填写供应商批次码 lot_code")

    return code
