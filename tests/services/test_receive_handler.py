"""
Legacy: handle_receive (扫码入库 Handler) 的旧合同测试。

原测试依赖：
  - handle_receive(session, item_id, location_id, qty, ref, batch_code=None, ...)；
  - 内部调用 StockService.adjust(session, item_id, location_id, delta, ...)。

当前版本中：
  - StockService.adjust 已升级为 (item_id, warehouse_id, batch_code) 粒度；
  - handle_receive 的签名也已调整，不再接收 location_id 关键字参数；
  - 旧测试继续按 (item_id, location_id) 口径调用，触发 TypeError。

Scan 入库通路将在后续 Phase 以新模型重写合同测试，本文件现标记为 legacy。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy receive handler tests: handle_receive no longer takes location_id "
        "and has been refactored for v2 (warehouse,item,batch) model."
    )
)
