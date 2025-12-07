"""
Legacy: 出库 FEFO 注入（需传 OutboundLine, mode='FEFO'）的 HTTP 合同测试。

原测试依赖：
  - from app.services.outbound_service import OutboundLine, OutboundService
  - OutboundService.commit(session, platform, shop_id, ref,
        lines=[OutboundLine(item_id, location_id, qty)], mode='FEFO', ...)

当前：
  - FEFO 行为由 v2 FefoAllocator/StockFallbacks 提供建议；
  - 出库 API 的主入口是 v2 OutboundService.commit(order_id, lines=[{warehouse_id, item_id, batch_code, qty}], ...)，
    而非 v1 的平台+location+mode 接口。

本文件视为旧 FEFO 接口的合同文档，标记为 legacy。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy outbound FEFO injection API test using OutboundService.commit "
        "with OutboundLine(location_id) and mode='FEFO'; superseded by v2 "
        "outbound/FEFO design."
    )
)
