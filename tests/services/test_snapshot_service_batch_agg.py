"""
Legacy: 快照服务 batch 聚合（v1 Inbound + location_id）测试。

原流程：
  - InboundService.receive(session, item_id, location_id, qty, ref, batch_code, expiry_date);
  - 使用 snapshot_inventory 产生按 (item, location) 聚合的批次快照；
  - 检查最新快照汇总是否等于实时库存汇总。

当前：
  - InboundService 接口与库存模型已升级为 v2 (warehouse_id, batch_code) 口径；
  - 快照视图/聚合逻辑已通过 v2 快照测试覆盖（test_snapshot_service*.py）。

本文件作为旧快照设计文档，标记为 legacy。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy snapshot-by-batch aggregation tests based on InboundService.receive(location_id); "
        "snapshot v2 behavior is covered by test_snapshot_service*.py."
    )
)
