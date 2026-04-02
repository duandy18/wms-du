# app/wms/procurement/services/purchase_order_receive.py
from __future__ import annotations

# 注意：本文件是 facade（薄门面），只做对外兼容导出。
# 真实逻辑请放在 app/services/receive/* 下，禁止把业务继续写回本文件。

from app.services.receive.receipt_draft import (  # noqa: F401
    get_or_create_po_draft_receipt_explicit,
)
from app.services.receive.receive_po_line import (  # noqa: F401
    receive_po_line,
)

__all__ = [
    "get_or_create_po_draft_receipt_explicit",
    "receive_po_line",
]
