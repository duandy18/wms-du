# app/wms/ledger/services/stock_service_adjust.py
"""
stock_service_adjust.py（稳定入口 + infra wrapper）

约束（audit-consistency）：
- 禁止在非白名单模块直接 await write_ledger()
- 白名单包含本文件，因此：
  - 任何库存写入实现想记账，都必须通过本文件的 write_ledger_infra()

Phase 4D/4E 目标：
- 从双轨到纯 stocks_lot
- stocks 逐步降级为 legacy / 可选 rebuild
"""

from __future__ import annotations

from typing import Any

from app.wms.ledger.services.ledger_writer import write_ledger as _write_ledger


async def write_ledger_infra(**kwargs: Any) -> Any:
    """
    ✅ infra wrapper: 允许模块内直接 await write_ledger()
    其他模块（例如 app/services/stock_adjust/*）必须调用本函数，而不能直接调用 write_ledger。
    """
    return await _write_ledger(**kwargs)


__all__ = [
    "write_ledger_infra",
]
