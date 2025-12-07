# app/services/outbound_metrics_v2.py

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.metrics_outbound_v2 import (
    FefoItemRisk,
    FefoRiskMetricsResponse,
    OutboundDaySummary,
    OutboundDistributionPoint,
    OutboundFailureDetail,
    OutboundFailuresMetricsResponse,
    OutboundMetricsV2,
    OutboundRangeMetricsResponse,
    OutboundShopMetric,
    OutboundShopMetricsResponse,
    OutboundWarehouseMetric,
    OutboundWarehouseMetricsResponse,
)

UTC = timezone.utc


class OutboundMetricsV2Service:
    """
    出库指标 v2 统一服务：
    - 单日大盘          (load_day)
    - 多日趋势          (load_range)
    - 仓库维度          (load_by_warehouse)
    - 失败诊断          (load_failures)
    - FEFO 风险监控     (load_fefo_risk)
    - 店铺维度          (load_by_shop)
    """

    # ---------------------------------------------------------
    # 基础：单日 + 单平台汇总
    # ---------------------------------------------------------

    async def load_day(
        self,
        session: AsyncSession,
        day: date,
        platform: str,
    ) -> OutboundMetricsV2:
        """
        复用你当前的 /metrics/outbound/today / {day} 需求，
        但直接返回 v2 结构。
        """

        # 1) 订单成功率
        orders_sql = text(
            """
            SELECT
                count(*) FILTER (WHERE (meta->>'event')='ORDER_CREATED') AS total,
                count(*) FILTER (WHERE (meta->>'event')='SHIP_COMMIT') AS success
            FROM audit_events
            WHERE category='OUTBOUND'
              AND (meta->>'platform') = :platform
              AND (created_at AT TIME ZONE 'utc')::date = :day
            """
        )
        r = await session.execute(orders_sql, {"platform": platform, "day": day})
        row = r.fetchone()
        total_orders = int(row.total or 0) if row else 0
        success_orders = int(row.success or 0) if row else 0
        if total_orders > 0:
            success_rate = round(success_orders * 100.0 / total_orders, 2)
        else:
            success_rate = 0.0

        # 2) fallback 指标（目前从 ROUTING 类审计事件中统计）
        routing_sql = text(
            """
            SELECT
                count(*) FILTER (WHERE meta->>'routing_event'='FALLBACK') AS fallback_times,
                count(*) FILTER (
                    WHERE meta->>'routing_event' IN ('REQUEST','FALLBACK','OK')
                ) AS total_routing
            FROM audit_events
            WHERE category='ROUTING'
              AND (meta->>'platform') = :platform
              AND (created_at AT TIME ZONE 'utc')::date = :day
            """
        )
        r = await session.execute(routing_sql, {"platform": platform, "day": day})
        row = r.fetchone()
        fallback_times = int((row and row.fallback_times) or 0)
        total_routing = int((row and row.total_routing) or 0)
        if total_routing > 0:
            fallback_rate = round(fallback_times * 100.0 / total_routing, 2)
        else:
            fallback_rate = 0.0

        # 3) FEFO 命中率（按 item 粒度判断实际扣减批次是否为最早到期）
        #    简化版：从 stock_ledger 中找当天的 PICK / OUTBOUND_* 扣减。
        pick_sql = text(
            """
            SELECT
                l.item_id,
                l.batch_code,
                l.warehouse_id,
                abs(l.delta) AS qty,
                l.occurred_at
            FROM stock_ledger l
            WHERE l.delta < 0
              AND l.reason IN ('PICK','OUTBOUND_SHIP','OUTBOUND_V2_SHIP','SHIP')
              AND (l.occurred_at AT TIME ZONE 'utc')::date = :day
            """
        )
        rows = (await session.execute(pick_sql, {"day": day})).fetchall()

        fefo_correct = 0
        fefo_total = 0

        for item_id, batch_code, wh_id, qty, occurred_at in rows:
            # 获取该 item 的所有批次到期日
            bsql = text(
                """
                SELECT batch_code, expiry_date
                FROM batches
                WHERE item_id = :item_id
                """
            )
            br = (await session.execute(bsql, {"item_id": item_id})).fetchall()
            if not br:
                continue  # 没有批次信息就不纳入统计

            # 找理论 FEFO 批次 = 最早 expiry 的批次
            sorted_batches = sorted(
                [(b.batch_code, b.expiry_date) for b in br],
                key=lambda x: x[1] or datetime.max.replace(tzinfo=None),
            )
            fefo_batch = sorted_batches[0][0]

            fefo_total += 1
            if batch_code == fefo_batch:
                fefo_correct += 1

        if fefo_total > 0:
            fefo_hit_rate = round(fefo_correct * 100.0 / fefo_total, 2)
        else:
            fefo_hit_rate = 0.0

        # 4) 当日按小时分布：订单 + 拣货量
        dist_orders_sql = text(
            """
            SELECT
                to_char(date_trunc('hour', created_at AT TIME ZONE 'utc'), 'HH24') AS hour,
                count(*) FILTER (WHERE (meta->>'event')='ORDER_CREATED') AS orders
            FROM audit_events
            WHERE category='OUTBOUND'
              AND (meta->>'platform') = :platform
              AND (created_at AT TIME ZONE 'utc')::date = :day
            GROUP BY 1
            ORDER BY 1
            """
        )
        dist_rows = (
            await session.execute(dist_orders_sql, {"platform": platform, "day": day})
        ).fetchall()

        dist_pick_sql = text(
            """
            SELECT
                to_char(date_trunc('hour', occurred_at AT TIME ZONE 'utc'), 'HH24') AS hour,
                sum(abs(delta)) AS pick_qty
            FROM stock_ledger
            WHERE delta < 0
              AND reason IN ('PICK','OUTBOUND_SHIP','OUTBOUND_V2_SHIP','SHIP')
              AND (occurred_at AT TIME ZONE 'utc')::date = :day
            GROUP BY 1
            ORDER BY 1
            """
        )
        pick_rows = (await session.execute(dist_pick_sql, {"day": day})).fetchall()
        picks_map = {r.hour: int(r.pick_qty or 0) for r in pick_rows}

        distribution: List[OutboundDistributionPoint] = []
        for r in dist_rows:
            distribution.append(
                OutboundDistributionPoint(
                    hour=r.hour,
                    orders=int(r.orders or 0),
                    pick_qty=picks_map.get(r.hour, 0),
                )
            )

        return OutboundMetricsV2(
            day=day,
            platform=platform,
            total_orders=total_orders,
            success_orders=success_orders,
            success_rate=success_rate,
            fallback_times=fallback_times,
            fallback_rate=fallback_rate,
            fefo_hit_rate=fefo_hit_rate,
            distribution=distribution,
        )

    # ---------------------------------------------------------
    # 多日趋势
    # ---------------------------------------------------------

    async def load_range(
        self,
        session: AsyncSession,
        platform: str,
        days: int,
        end_day: Optional[date] = None,
    ) -> OutboundRangeMetricsResponse:
        """
        最近 N 天趋势（含 end_day 当天，默认 = 今天）
        """
        if end_day is None:
            end_day = datetime.now(UTC).date()

        # 由近到远，组装 day 列表
        day_list: List[date] = [end_day - timedelta(days=i) for i in range(days)]
        day_list.sort()

        summaries: List[OutboundDaySummary] = []
        for d in day_list:
            m = await self.load_day(session=session, day=d, platform=platform)
            summaries.append(
                OutboundDaySummary(
                    day=m.day,
                    total_orders=m.total_orders,
                    success_rate=m.success_rate,
                    fallback_rate=m.fallback_rate,
                    fefo_hit_rate=m.fefo_hit_rate,
                )
            )

        return OutboundRangeMetricsResponse(platform=platform, days=summaries)

    # ---------------------------------------------------------
    # 仓库维度（按 wh 拆）
    # ---------------------------------------------------------

    async def load_by_warehouse(
        self,
        session: AsyncSession,
        day: date,
        platform: str,
    ) -> OutboundWarehouseMetricsResponse:
        """
        仓库维度的基础统计：
        - total_orders: 当日该仓发生过拣货/出库的订单数（按 ref 去重）
        - success_orders: 有 SHIP_COMMIT 的订单数（按 ref 去重）
        - pick_qty: 拣货件数
        """
        sql = text(
            """
            WITH picks AS (
                SELECT
                    l.warehouse_id,
                    l.ref,
                    sum(abs(l.delta)) AS pick_qty
                FROM stock_ledger l
                JOIN audit_events ae
                  ON ae.ref = l.ref
                 AND ae.category='OUTBOUND'
                 AND (ae.meta->>'platform') = :platform
                WHERE l.delta < 0
                  AND l.reason IN ('PICK','OUTBOUND_SHIP','OUTBOUND_V2_SHIP','SHIP')
                  AND (l.occurred_at AT TIME ZONE 'utc')::date = :day
                GROUP BY l.warehouse_id, l.ref
            ),
            orders AS (
                SELECT
                    p.warehouse_id,
                    p.ref,
                    bool_or(ae.meta->>'event' = 'SHIP_COMMIT') AS shipped
                FROM picks p
                JOIN audit_events ae
                  ON ae.ref = p.ref
                 AND ae.category='OUTBOUND'
                GROUP BY p.warehouse_id, p.ref
            )
            SELECT
                o.warehouse_id,
                count(*) AS total_orders,
                count(*) FILTER (WHERE o.shipped) AS success_orders,
                sum(p.pick_qty) AS pick_qty
            FROM orders o
            JOIN picks p
              ON p.warehouse_id = o.warehouse_id
             AND p.ref = o.ref
            GROUP BY o.warehouse_id
            ORDER BY o.warehouse_id
            """
        )
        rows = (await session.execute(sql, {"platform": platform, "day": day})).fetchall()

        wh_metrics: List[OutboundWarehouseMetric] = []
        for r in rows:
            wh_id = int(r.warehouse_id)
            total = int(r.total_orders or 0)
            success = int(r.success_orders or 0)
            pick_qty = int(r.pick_qty or 0)
            success_rate = round(success * 100.0 / total, 2) if total > 0 else 0.0
            wh_metrics.append(
                OutboundWarehouseMetric(
                    warehouse_id=wh_id,
                    total_orders=total,
                    success_orders=success,
                    success_rate=success_rate,
                    pick_qty=pick_qty,
                )
            )

        return OutboundWarehouseMetricsResponse(
            day=day,
            platform=platform,
            warehouses=wh_metrics,
        )

    # ---------------------------------------------------------
    # 出库失败诊断（Routing / Pick / Ship / Inventory）
    # ---------------------------------------------------------

    async def load_failures(
        self,
        session: AsyncSession,
        day: date,
        platform: str,
    ) -> OutboundFailuresMetricsResponse:
        """
        简化版失败统计：
        - 从 audit_events 中找 category='OUTBOUND_FAIL' / 'ROUTING'
        - meta.routing_event / meta.event 来区分失败类型
        """
        fail_sql = text(
            """
            SELECT
                ref,
                meta->>'trace_id' AS trace_id,
                meta->>'fail_point' AS fail_point,
                meta->>'message' AS message
            FROM audit_events
            WHERE category IN ('OUTBOUND_FAIL','ROUTING')
              AND (meta->>'platform') = :platform
              AND (created_at AT TIME ZONE 'utc')::date = :day
            """
        )
        rows = (await session.execute(fail_sql, {"platform": platform, "day": day})).fetchall()

        routing_failed = 0
        pick_failed = 0
        ship_failed = 0
        inventory_insufficient = 0
        details: List[OutboundFailureDetail] = []

        for r in rows:
            fail_point_raw = (r.fail_point or "").upper()
            if fail_point_raw == "ROUTING_FAIL":
                routing_failed += 1
                fail_point = "ROUTING_FAIL"
            elif fail_point_raw == "PICK_FAIL":
                pick_failed += 1
                fail_point = "PICK_FAIL"
            elif fail_point_raw == "SHIP_FAIL":
                ship_failed += 1
                fail_point = "SHIP_FAIL"
            elif fail_point_raw == "INVENTORY_FAIL":
                inventory_insufficient += 1
                fail_point = "INVENTORY_FAIL"
            else:
                fail_point = fail_point_raw or "UNKNOWN"

            details.append(
                OutboundFailureDetail(
                    ref=r.ref,
                    trace_id=r.trace_id,
                    fail_point=fail_point,
                    message=r.message,
                )
            )

        return OutboundFailuresMetricsResponse(
            day=day,
            platform=platform,
            routing_failed=routing_failed,
            pick_failed=pick_failed,
            ship_failed=ship_failed,
            inventory_insufficient=inventory_insufficient,
            details=details,
        )

    # ---------------------------------------------------------
    # FEFO 风险监控（最近 7 天）
    # ---------------------------------------------------------

    async def load_fefo_risk(
        self,
        session: AsyncSession,
        days: int = 7,
    ) -> FefoRiskMetricsResponse:
        """
        简化版 FEFO 风险：
        - near_expiry_batches: 未来 30 天内到期的批次数
        - fefo_hit_rate_7d: 最近 N 天的 FEFO 命中率
        - risk_score: 结合 near_expiry_batches & 命中率 反向，简单打分
        """
        today = datetime.now(UTC).date()
        horizon = today + timedelta(days=30)
        since_day = today - timedelta(days=days)

        # 1) 找 near expiry 批次
        near_sql = text(
            """
            SELECT
                b.item_id,
                count(*) AS near_batches
            FROM batches b
            WHERE b.expiry_date IS NOT NULL
              AND b.expiry_date::date BETWEEN :today AND :horizon
            GROUP BY b.item_id
            """
        )
        near_rows = (
            await session.execute(near_sql, {"today": today, "horizon": horizon})
        ).fetchall()
        near_map: Dict[int, int] = {int(r.item_id): int(r.near_batches or 0) for r in near_rows}

        if not near_map:
            return FefoRiskMetricsResponse(as_of=today, items=[])

        # 2) 这些 item 在最近 N 天的 FEFO 命中情况
        pick_sql = text(
            """
            SELECT
                l.item_id,
                l.batch_code,
                abs(l.delta) AS qty
            FROM stock_ledger l
            WHERE l.delta < 0
              AND l.reason IN ('PICK','OUTBOUND_SHIP','OUTBOUND_V2_SHIP','SHIP')
              AND (l.occurred_at AT TIME ZONE 'utc')::date BETWEEN :since_day AND :today
              AND l.item_id = ANY(:item_ids)
            """
        )
        item_ids = list(near_map.keys())
        pick_rows = (
            await session.execute(
                pick_sql, {"since_day": since_day, "today": today, "item_ids": item_ids}
            )
        ).fetchall()

        # 按 item 收集 pick 批次
        picks_by_item: Dict[int, List[str]] = {}
        for item_id, batch_code, qty in pick_rows:
            if item_id not in picks_by_item:
                picks_by_item[item_id] = []
            picks_by_item[item_id].append(batch_code)

        items_risk: List[FefoItemRisk] = []

        for item_id, near_batches in near_map.items():
            # 找理论 FEFO 批次
            bsql = text(
                """
                SELECT batch_code, expiry_date
                FROM batches
                WHERE item_id = :item_id
                  AND expiry_date IS NOT NULL
                """
            )
            br = (await session.execute(bsql, {"item_id": item_id})).fetchall()
            if not br:
                continue

            sorted_batches = sorted(
                [(b.batch_code, b.expiry_date) for b in br],
                key=lambda x: x[1] or datetime.max.replace(tzinfo=None),
            )
            fefo_batch = sorted_batches[0][0]

            pick_codes = picks_by_item.get(item_id, [])
            if pick_codes:
                total_picks = len(pick_codes)
                fefo_picks = sum(1 for c in pick_codes if c == fefo_batch)
                fefo_hit = round(fefo_picks * 100.0 / total_picks, 2)
            else:
                fefo_hit = 0.0

            # 3) 取 items 主数据
            item_sql = text("SELECT id, sku, name FROM items WHERE id = :item_id")
            ir = (await session.execute(item_sql, {"item_id": item_id})).fetchone()
            sku = ir.sku if ir else f"ITEM-{item_id}"
            name = ir.name if ir else ""

            # 4) 简单打分：near_batch 多、命中率低 → 风险高
            risk_score = min(
                100.0,
                max(0.0, near_batches * 10.0 + max(0.0, 50.0 - fefo_hit)),
            )

            items_risk.append(
                FefoItemRisk(
                    item_id=item_id,
                    sku=sku,
                    name=name,
                    near_expiry_batches=near_batches,
                    fefo_hit_rate_7d=fefo_hit,
                    risk_score=round(risk_score, 2),
                )
            )

        # 按风险分数排序
        items_risk.sort(key=lambda x: x.risk_score, reverse=True)

        return FefoRiskMetricsResponse(as_of=today, items=items_risk)

    # ---------------------------------------------------------
    # 店铺维度：platform + shop_id
    # ---------------------------------------------------------

    async def load_by_shop(
        self,
        session: AsyncSession,
        day: date,
        platform: str,
    ) -> OutboundShopMetricsResponse:
        """
        按店铺维度拆分：
        - 依赖 audit_events.meta 里的 shop_id（如果没有，就归为 'UNKNOWN'）
        """
        sql = text(
            """
            WITH orders AS (
                SELECT
                    COALESCE(meta->>'shop_id', 'UNKNOWN') AS shop_id,
                    meta->>'event' AS event,
                    ref
                FROM audit_events
                WHERE category='OUTBOUND'
                  AND (meta->>'platform') = :platform
                  AND (created_at AT TIME ZONE 'utc')::date = :day
            )
            SELECT
                shop_id,
                count(*) FILTER (WHERE event='ORDER_CREATED') AS total_orders,
                count(*) FILTER (WHERE event='SHIP_COMMIT') AS success_orders
            FROM orders
            GROUP BY shop_id
            ORDER BY shop_id
            """
        )
        rows = (await session.execute(sql, {"platform": platform, "day": day})).fetchall()

        # fallback 次数按 shop 粒度目前只做粗糙分布（如有 routing 审计可进一步细化）
        routing_sql = text(
            """
            SELECT
                COALESCE(meta->>'shop_id', 'UNKNOWN') AS shop_id,
                count(*) FILTER (WHERE meta->>'routing_event'='FALLBACK') AS fallback_times,
                count(*) FILTER (
                    WHERE meta->>'routing_event' IN ('REQUEST','FALLBACK','OK')
                ) AS total_routing
            FROM audit_events
            WHERE category='ROUTING'
              AND (meta->>'platform') = :platform
              AND (created_at AT TIME ZONE 'utc')::date = :day
            GROUP BY shop_id
            """
        )
        r_rows = (await session.execute(routing_sql, {"platform": platform, "day": day})).fetchall()
        routing_map: Dict[str, Tuple[int, int]] = {
            str(r.shop_id): (int(r.fallback_times or 0), int(r.total_routing or 0)) for r in r_rows
        }

        shops: List[OutboundShopMetric] = []
        for r in rows:
            shop_id = str(r.shop_id)
            total = int(r.total_orders or 0)
            success = int(r.success_orders or 0)
            if total > 0:
                success_rate = round(success * 100.0 / total, 2)
            else:
                success_rate = 0.0

            fb_times, fb_total = routing_map.get(shop_id, (0, 0))
            if fb_total > 0:
                fb_rate = round(fb_times * 100.0 / fb_total, 2)
            else:
                fb_rate = 0.0

            shops.append(
                OutboundShopMetric(
                    shop_id=shop_id,
                    total_orders=total,
                    success_orders=success,
                    success_rate=success_rate,
                    fallback_times=fb_times,
                    fallback_rate=fb_rate,
                )
            )

        return OutboundShopMetricsResponse(
            day=day,
            platform=platform,
            shops=shops,
        )
