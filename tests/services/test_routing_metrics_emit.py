# tests/services/test_routing_metrics_emit.py

from app.metrics import routing as routing_metrics


class FakeCounter:
    def __init__(self):
        # 每次调用 labels() 会 append 一个 dict，记录 labels 和 inc 次数
        self.calls: list[dict] = []

    def labels(self, **labels):
        self.calls.append({"labels": labels, "count": 0})
        return self

    def inc(self):
        if not self.calls:
            self.calls.append({"labels": {}, "count": 0})
        self.calls[-1]["count"] += 1


def test_routing_metrics_emit_success_and_fallback():
    """
    验证 RoutingDecision -> Counter.labels(...).inc() 的调用逻辑：
    1. 成功决策（fallback 场景）：
       - decisions_total 记录 result="ok"、selected_warehouse_id
       - warehouse_routed_orders_total 记录 is_fallback="true"
       - fallback_total 记录 from_warehouse_id / to_warehouse_id
    2. 失败决策（no_candidate）：
       - decisions_total 再记一笔 result="no_candidate"
       - no_warehouse_total 记录 reason
    """

    # 用 FakeCounter 覆盖模块内的全局 Counter
    decisions = FakeCounter()
    fallback = FakeCounter()
    no_wh = FakeCounter()
    wh_orders = FakeCounter()

    routing_metrics._ROUTING_DECISIONS_TOTAL = decisions
    routing_metrics._ROUTING_FALLBACK_TOTAL = fallback
    routing_metrics._ROUTING_NO_WAREHOUSE_TOTAL = no_wh
    routing_metrics._WAREHOUSE_ROUTED_ORDERS_TOTAL = wh_orders

    # -----------------------------
    # Case 1：Fallback 成功决策
    # -----------------------------
    decision_ok = routing_metrics.RoutingDecision(
        platform="PDD",
        shop_id="1",
        route_mode="FALLBACK",
        result="ok",
        selected_warehouse_id=2,
        primary_warehouse_id=1,
        is_fallback=True,
        reason="fallback_selected",
    )
    routing_metrics.record_decision(decision_ok)

    # decisions_total 应被调用一次
    assert len(decisions.calls) == 1
    dec_call = decisions.calls[0]
    assert dec_call["count"] == 1
    assert dec_call["labels"]["platform"] == "PDD"
    assert dec_call["labels"]["shop_id"] == "1"
    assert dec_call["labels"]["route_mode"] == "FALLBACK"
    assert dec_call["labels"]["result"] == "ok"
    assert dec_call["labels"]["selected_warehouse_id"] == "2"

    # warehouse_routed_orders_total 也被调用一次，且 is_fallback=true
    assert len(wh_orders.calls) == 1
    wh_call = wh_orders.calls[0]
    assert wh_call["count"] == 1
    assert wh_call["labels"]["warehouse_id"] == "2"
    assert wh_call["labels"]["is_fallback"] == "true"

    # fallback_total 被调用一次，from=1 -> to=2
    assert len(fallback.calls) == 1
    fb_call = fallback.calls[0]
    assert fb_call["count"] == 1
    assert fb_call["labels"]["from_warehouse_id"] == "1"
    assert fb_call["labels"]["to_warehouse_id"] == "2"
    assert fb_call["labels"]["reason"] == "fallback_selected"

    # -----------------------------
    # Case 2：无仓可履约
    # -----------------------------
    decision_fail = routing_metrics.RoutingDecision(
        platform="PDD",
        shop_id="1",
        route_mode="FALLBACK",
        result="no_candidate",
        selected_warehouse_id=None,
        primary_warehouse_id=1,
        is_fallback=False,
        reason="no_warehouse_can_fulfill",
    )
    routing_metrics.record_decision(decision_fail)

    # decisions_total 再多一条记录
    assert len(decisions.calls) == 2
    dec_fail = decisions.calls[1]
    assert dec_fail["labels"]["result"] == "no_candidate"

    # no_warehouse_total 应被调用一次
    assert len(no_wh.calls) == 1
    no_wh_call = no_wh.calls[0]
    assert no_wh_call["count"] == 1
    assert no_wh_call["labels"]["platform"] == "PDD"
    assert no_wh_call["labels"]["shop_id"] == "1"
    assert no_wh_call["labels"]["route_mode"] == "FALLBACK"
    assert no_wh_call["labels"]["reason"] == "no_warehouse_can_fulfill"
