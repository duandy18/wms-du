# app/metrics/routing.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from prometheus_client import REGISTRY, CollectorRegistry, Counter

# 这里的 registry 复用全局 REGISTRY，
# 如果你有自定义 registry，可以改成从 app settings 注入。
_registry: CollectorRegistry = REGISTRY


@dataclass(frozen=True)
class RoutingDecision:
    platform: str
    shop_id: str
    route_mode: str  # "FALLBACK" / "STRICT_TOP" / ...
    result: str  # "ok" / "no_candidate"
    selected_warehouse_id: Optional[int]
    primary_warehouse_id: Optional[int]
    is_fallback: bool
    reason: Optional[str] = None  # "insufficient_main" / "no_config" / ...


# ---- Prometheus metrics definitions --------------------------------------


# 所有路由请求（不管成功失败）
_ROUTING_REQUESTS_TOTAL = Counter(
    "wmsdu_routing_requests_total",
    "Total routing requests received",
    ["platform", "shop_id", "route_mode"],
    registry=_registry,
)

# 路由决策结果（成功/失败）
_ROUTING_DECISIONS_TOTAL = Counter(
    "wmsdu_routing_decisions_total",
    "Total routing decisions made (success or failure)",
    ["platform", "shop_id", "route_mode", "result", "selected_warehouse_id"],
    registry=_registry,
)

# fallback 次数
_ROUTING_FALLBACK_TOTAL = Counter(
    "wmsdu_routing_fallback_total",
    "Total fallback routing decisions (main warehouse could not fulfill, "
    "fallback warehouse selected instead)",
    [
        "platform",
        "shop_id",
        "route_mode",
        "from_warehouse_id",
        "to_warehouse_id",
        "reason",
    ],
    registry=_registry,
)

# 无仓可履约次数
_ROUTING_NO_WAREHOUSE_TOTAL = Counter(
    "wmsdu_routing_no_warehouse_total",
    "Total routing failures where no warehouse can fulfill the order",
    ["platform", "shop_id", "route_mode", "reason"],
    registry=_registry,
)

# 每仓被分配为履约仓次数（按订单）
_WAREHOUSE_ROUTED_ORDERS_TOTAL = Counter(
    "wmsdu_warehouse_routed_orders_total",
    "Total number of orders routed to a warehouse",
    ["platform", "shop_id", "route_mode", "warehouse_id", "is_fallback"],
    registry=_registry,
)


def record_request(platform: str, shop_id: str, route_mode: str) -> None:
    """
    在进入路由函数的第一行调用，表示有一次路由请求。
    """
    _ROUTING_REQUESTS_TOTAL.labels(
        platform=platform,
        shop_id=shop_id,
        route_mode=route_mode,
    ).inc()


def record_decision(decision: RoutingDecision) -> None:
    """
    在路由决策完成、写入 orders.warehouse_id 之后调用。
    """
    platform = decision.platform
    shop_id = decision.shop_id
    route_mode = decision.route_mode
    result = decision.result
    selected_wh = str(decision.selected_warehouse_id or 0)

    # 1) 总决策
    _ROUTING_DECISIONS_TOTAL.labels(
        platform=platform,
        shop_id=shop_id,
        route_mode=route_mode,
        result=result,
        selected_warehouse_id=selected_wh,
    ).inc()

    # 2) 无仓可履约
    if result == "no_candidate":
        _ROUTING_NO_WAREHOUSE_TOTAL.labels(
            platform=platform,
            shop_id=shop_id,
            route_mode=route_mode,
            reason=decision.reason or "unknown",
        ).inc()
        # 失败情况下就不再记录 warehouse_routed_orders
        return

    # 3) 成功情况下，记录仓利用率视角（“被分配到这个仓”的订单数）
    if decision.selected_warehouse_id is not None:
        _WAREHOUSE_ROUTED_ORDERS_TOTAL.labels(
            platform=platform,
            shop_id=shop_id,
            route_mode=route_mode,
            warehouse_id=str(decision.selected_warehouse_id),
            is_fallback="true" if decision.is_fallback else "false",
        ).inc()

    # 4) fallback 情况
    if decision.is_fallback and decision.selected_warehouse_id is not None:
        _ROUTING_FALLBACK_TOTAL.labels(
            platform=platform,
            shop_id=shop_id,
            route_mode=route_mode,
            from_warehouse_id=str(decision.primary_warehouse_id or 0),
            to_warehouse_id=str(decision.selected_warehouse_id),
            reason=decision.reason or "insufficient_main",
        ).inc()
