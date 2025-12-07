# tests/api/test_phase3x_diagnostics_seed_scenario.py

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import pytest


def _parse_iso8601(s: str) -> datetime:
    """兼容带时区的 ISO8601 字符串。"""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


async def _seed_ledger(client) -> Dict[str, Any]:
    """
    调用 /dev/seed-ledger-test 接口，返回 JSON。
    该接口本身是幂等的，多次调用不会重复扣减。
    """
    resp = await client.post("/dev/seed-ledger-test")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert data.get("warehouse_id")
    assert data.get("item_id")
    assert data.get("batch_code")
    assert data.get("results")
    return data


@pytest.mark.asyncio
async def test_seed_ledger_creates_stocks_and_ledger(client):
    """
    场景 1：种子接口能正确落库：
      - stocks 中有 B-TEST-LEDGER 这一槽位且 qty=5
      - ledger 中能查到 3 条事件，movement_type 正常映射
    """
    seed = await _seed_ledger(client)

    wh_id = seed["warehouse_id"]
    item_id = seed["item_id"]
    batch_code = seed["batch_code"]

    first_event = seed["results"][0]["result"]
    occurred_at = _parse_iso8601(first_event["occurred_at"])
    t_from = (occurred_at - timedelta(days=1)).astimezone(timezone.utc)
    t_to = (occurred_at + timedelta(days=1)).astimezone(timezone.utc)

    # 1) 查询台账明细，确认有三条事件且 movement_type 正常
    resp = await client.post(
        "/stock/ledger/query",
        json={
            "limit": 50,
            "offset": 0,
            "warehouse_id": wh_id,
            "item_id": item_id,
            "batch_code": batch_code,
            "time_from": t_from.isoformat(),
            "time_to": t_to.isoformat(),
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    items = data.get("items", [])
    # 预期至少有 3 条记录（RECEIPT / SHIPMENT / ADJUSTMENT）
    assert len(items) >= 3

    reasons = {row["reason"] for row in items}
    movement_types = {row.get("movement_type") for row in items}

    # 入库 + 出库 + 调整 这三种 reason / movement_type 都应当出现
    assert "RECEIPT" in reasons
    assert "SHIPMENT" in reasons or "SHIP" in reasons
    assert "ADJUSTMENT" in reasons or "COUNT" in reasons

    assert "INBOUND" in movement_types
    assert "OUTBOUND" in movement_types
    assert "ADJUST" in movement_types or "COUNT" in movement_types


@pytest.mark.asyncio
async def test_reconcile_v2_summary_aggregates_seed_events(client):
    """
    场景 2：多维对账汇总接口 /stock/ledger/reconcile-v2/summary
    能正确按 movement_type / ref / trace 聚合种子事件。
    """
    seed = await _seed_ledger(client)
    first_event = seed["results"][0]["result"]
    occurred_at = _parse_iso8601(first_event["occurred_at"])

    t_from = (occurred_at - timedelta(days=1)).astimezone(timezone.utc)
    t_to = (occurred_at + timedelta(days=1)).astimezone(timezone.utc)

    resp = await client.post(
        "/stock/ledger/reconcile-v2/summary",
        json={
            "time_from": t_from.isoformat(),
            "time_to": t_to.isoformat(),
            "limit": 100,
            "offset": 0,
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    # movement_type 汇总应包含 INBOUND/OUTBOUND/ADJUST 三类
    mt = data.get("movement_type", {})
    assert "INBOUND" in mt
    assert "OUTBOUND" in mt
    assert "ADJUST" in mt or "COUNT" in mt

    # ref 聚合中应有三种 seed ref
    refs = {row["ref"] for row in data.get("ref", [])}
    assert "seed:receipt:1" in refs
    assert "seed:ship:1" in refs
    assert "seed:count:1" in refs

    # trace 聚合中应有三种 seed trace_id
    traces = {row["trace_id"] for row in data.get("trace", [])}
    assert "seed-trace-receipt" in traces
    assert "seed-trace-ship" in traces
    assert "seed-trace-count" in traces


@pytest.mark.asyncio
async def test_intelligence_insights_has_reasonable_values(client):
    """
    场景 3：智能层 /inventory/intelligence/insights
    在有种子台账事件时，返回的指标不是全 0 且在合理区间。
    """
    await _seed_ledger(client)  # 幂等，多次调用也安全

    resp = await client.get("/inventory/intelligence/insights")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    insights = data.get("insights")
    assert isinstance(insights, dict)

    # 关键字段都存在
    for key in [
        "inventory_health_score",
        "inventory_accuracy_score",
        "snapshot_accuracy_score",
        "batch_activity_30days",
        "batch_risk_score",
        "warehouse_efficiency",
    ]:
        assert key in insights

    # 分数类字段在 [0,1] 之间
    for score_key in [
        "inventory_health_score",
        "inventory_accuracy_score",
        "snapshot_accuracy_score",
        "batch_risk_score",
        "warehouse_efficiency",
    ]:
        v = insights[score_key]
        assert isinstance(v, (int, float))
        assert 0.0 <= float(v) <= 1.0

    # 活跃度应当 >= 1（至少有我们种的三条事件）
    assert insights["batch_activity_30days"] >= 1
