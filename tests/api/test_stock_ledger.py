"""
Legacy API test: legacy stock ledger HTTP query contract using stock_service fixture and location-based adjust()

本文件对应的是接口早期设计的合同（多为 location_id / v1 StockService /
自动从 sku 建 order_items.item_id / 旧 scan 网关等），
当前实现已经升级为 v2 模型（warehouse+batch+SoftReserve），
并由新的 tests 覆盖行为。

此处仅保留为历史文档，不再参与当前测试基线。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason="legacy stock ledger HTTP query contract using stock_service fixture and location-based adjust()"
)
