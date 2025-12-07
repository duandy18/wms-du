# app/api/routers/finance_overview.py
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session

router = APIRouter(prefix="/finance", tags=["finance"])


class FinanceDailyRow(BaseModel):
    day: date
    revenue: Decimal
    purchase_cost: Decimal
    shipping_cost: Decimal
    gross_profit: Decimal
    gross_margin: Optional[Decimal] = None
    fulfillment_ratio: Optional[Decimal] = None


class FinanceShopRow(BaseModel):
    platform: str
    shop_id: str
    revenue: Decimal
    purchase_cost: Decimal
    shipping_cost: Decimal
    gross_profit: Decimal
    gross_margin: Optional[Decimal] = None
    fulfillment_ratio: Optional[Decimal] = None


class FinanceSkuRow(BaseModel):
    item_id: int
    sku_id: Optional[str] = None
    title: Optional[str] = None
    qty_sold: int
    revenue: Decimal
    purchase_cost: Decimal
    gross_profit: Decimal
    gross_margin: Optional[Decimal] = None


class OrderUnitSummary(BaseModel):
    order_count: int
    revenue: Decimal
    avg_order_value: Optional[Decimal] = None
    median_order_value: Optional[Decimal] = None


class OrderUnitContributionPoint(BaseModel):
    percent_orders: float  # 0~1
    percent_revenue: float  # 0~1


class OrderUnitRow(BaseModel):
    order_id: int
    platform: str
    shop_id: str
    ext_order_no: str
    order_value: Decimal
    created_at: str  # ISO 字符串


def _parse_date_param(value: Optional[str]) -> Optional[date]:
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None
    return date.fromisoformat(v)


# ---------------------------------------------------------------------------
# /finance/overview/daily
# ---------------------------------------------------------------------------


@router.get(
    "/overview/daily",
    response_model=List[FinanceDailyRow],
    summary="按日汇总的收入 / 成本 / 毛利趋势（运营视角粗粒度）",
)
async def finance_overview_daily(
    session: AsyncSession = Depends(get_session),
    current_user: Any = Depends(get_current_user),
    from_date: Optional[str] = Query(
        None,
        description="起始日期（YYYY-MM-DD，含）。默认=今天往前 6 天。",
    ),
    to_date: Optional[str] = Query(
        None,
        description="结束日期（YYYY-MM-DD，含）。默认=今天。",
    ),
) -> List[FinanceDailyRow]:
    """
    财务总览（按日）——运营视角粗估版本：

    - 收入：orders.pay_amount（缺失则退回 order_amount），按 orders.created_at::date 汇总
    - 商品成本：以 purchase_order_lines 的平均单价（总金额 / 总最小单位数）粗算，
                再乘以 order_items.qty（忽略退货与发货时点，只按订单创建日统计）
    - 发货成本：shipping_records.cost_estimated，按 shipping_records.created_at::date 汇总
    """
    from_dt = _parse_date_param(from_date)
    to_dt = _parse_date_param(to_date)

    # 默认最近 7 天
    if from_dt is None or to_dt is None:
        sql_default = text("SELECT current_date AS today")
        today_row = (await session.execute(sql_default)).mappings().first()
        today: date = today_row["today"]  # type: ignore[assignment]
        to_dt = today
        from_dt = date.fromordinal(today.toordinal() - 6)

    sql = text(
        """
        WITH day_dim AS (
          SELECT generate_series(:from_date, :to_date, interval '1 day')::date AS day
        ),
        item_cost AS (
          SELECT
            pol.item_id,
            COALESCE(SUM(COALESCE(pol.line_amount, 0)), 0) AS total_amount,
            COALESCE(SUM(pol.qty_ordered * COALESCE(pol.units_per_case, 1)), 0) AS total_units
          FROM purchase_orders po
          JOIN purchase_order_lines pol ON pol.po_id = po.id
          GROUP BY pol.item_id
        ),
        item_avg_cost AS (
          SELECT
            item_id,
            CASE
              WHEN total_units > 0 THEN total_amount / total_units
              ELSE NULL
            END AS avg_unit_cost
          FROM item_cost
        ),
        order_line_cost AS (
          SELECT
            DATE(o.created_at) AS day,
            SUM(
              COALESCE(oi.qty, 0) * COALESCE(iac.avg_unit_cost, 0)
            ) AS total_purchase_cost
          FROM orders o
          JOIN order_items oi ON oi.order_id = o.id
          LEFT JOIN item_avg_cost iac ON iac.item_id = oi.item_id
          WHERE DATE(o.created_at) BETWEEN :from_date AND :to_date
          GROUP BY DATE(o.created_at)
        ),
        order_revenue AS (
          SELECT
            DATE(o.created_at) AS day,
            SUM(
              COALESCE(o.pay_amount, o.order_amount, 0)
            ) AS total_revenue
          FROM orders o
          WHERE DATE(o.created_at) BETWEEN :from_date AND :to_date
          GROUP BY DATE(o.created_at)
        ),
        ship_cost AS (
          SELECT
            DATE(created_at) AS day,
            SUM(COALESCE(cost_estimated, 0)) AS total_shipping_cost
          FROM shipping_records
          WHERE DATE(created_at) BETWEEN :from_date AND :to_date
          GROUP BY DATE(created_at)
        )
        SELECT
          d.day AS day,
          COALESCE(orev.total_revenue, 0)       AS revenue,
          COALESCE(oc.total_purchase_cost, 0)   AS purchase_cost,
          COALESCE(sc.total_shipping_cost, 0)   AS shipping_cost
        FROM day_dim d
        LEFT JOIN order_revenue   orev ON orev.day = d.day
        LEFT JOIN order_line_cost oc   ON oc.day   = d.day
        LEFT JOIN ship_cost       sc   ON sc.day   = d.day
        ORDER BY d.day ASC
        """
    )

    result = await session.execute(
        sql,
        {
            "from_date": from_dt,
            "to_date": to_dt,
        },
    )
    rows = result.mappings().all()

    items: List[FinanceDailyRow] = []
    for row in rows:
        day: date = row["day"]
        revenue = Decimal(str(row["revenue"] or 0))
        purchase_cost = Decimal(str(row["purchase_cost"] or 0))
        shipping_cost = Decimal(str(row["shipping_cost"] or 0))

        gross_profit = revenue - purchase_cost - shipping_cost

        if revenue > 0:
            gross_margin = (gross_profit / revenue).quantize(Decimal("0.0001"))
            fulfillment_ratio = (shipping_cost / revenue).quantize(
                Decimal("0.0001"),
            )
        else:
            gross_margin = None
            fulfillment_ratio = None

        items.append(
            FinanceDailyRow(
                day=day,
                revenue=revenue,
                purchase_cost=purchase_cost,
                shipping_cost=shipping_cost,
                gross_profit=gross_profit,
                gross_margin=gross_margin,
                fulfillment_ratio=fulfillment_ratio,
            )
        )

    return items


# ---------------------------------------------------------------------------
# /finance/shop
# ---------------------------------------------------------------------------


@router.get(
    "/shop",
    response_model=List[FinanceShopRow],
    summary="按店铺聚合的收入 / 成本 / 毛利（运营视角粗粒度）",
)
async def finance_by_shop(
    session: AsyncSession = Depends(get_session),
    current_user: Any = Depends(get_current_user),
    from_date: Optional[str] = Query(
        None,
        description="起始日期（YYYY-MM-DD，含）。默认=今天往前 6 天。",
    ),
    to_date: Optional[str] = Query(
        None,
        description="结束日期（YYYY-MM-DD，含）。默认=今天。",
    ),
    platform: Optional[str] = Query(
        None,
        description="按平台过滤，例如 PDD / JD（可选）",
    ),
    shop_id: Optional[str] = Query(
        None,
        description="按店铺 ID 过滤（可选）",
    ),
) -> List[FinanceShopRow]:
    """
    店铺盈利能力（粗粒度）：

    - 收入：orders.pay_amount（缺失则退回 order_amount），按平台 / 店铺汇总
    - 商品成本：基于 purchase_order_lines 推导的 avg_unit_cost × order_items.qty
    - 发货成本：shipping_records.cost_estimated，按平台 / 店铺汇总

    说明：
    - plat='' / shop='' 表示“不过滤”，避免 asyncpg 对 NULL 参数类型歧义。
    """
    from_dt = _parse_date_param(from_date)
    to_dt = _parse_date_param(to_date)

    if from_dt is None or to_dt is None:
        sql_default = text("SELECT current_date AS today")
        today_row = (await session.execute(sql_default)).mappings().first()
        today: date = today_row["today"]  # type: ignore[assignment]
        to_dt = today
        from_dt = date.fromordinal(today.toordinal() - 6)

    plat = (platform or "").strip().upper()
    shop = (shop_id or "").strip()

    sql = text(
        """
        WITH item_cost AS (
          SELECT
            pol.item_id,
            COALESCE(SUM(COALESCE(pol.line_amount, 0)), 0) AS total_amount,
            COALESCE(SUM(pol.qty_ordered * COALESCE(pol.units_per_case, 1)), 0) AS total_units
          FROM purchase_orders po
          JOIN purchase_order_lines pol ON pol.po_id = po.id
          GROUP BY pol.item_id
        ),
        item_avg_cost AS (
          SELECT
            item_id,
            CASE
              WHEN total_units > 0 THEN total_amount / total_units
              ELSE NULL
            END AS avg_unit_cost
          FROM item_cost
        ),
        order_line_cost_shop AS (
          SELECT
            o.platform,
            o.shop_id,
            SUM(
              COALESCE(oi.qty, 0) * COALESCE(iac.avg_unit_cost, 0)
            ) AS total_purchase_cost
          FROM orders o
          JOIN order_items oi ON oi.order_id = o.id
          LEFT JOIN item_avg_cost iac ON iac.item_id = oi.item_id
          WHERE DATE(o.created_at) BETWEEN :from_date AND :to_date
            AND (:plat = '' OR o.platform = :plat)
            AND (:shop = '' OR o.shop_id = :shop)
          GROUP BY o.platform, o.shop_id
        ),
        order_revenue_shop AS (
          SELECT
            o.platform,
            o.shop_id,
            SUM(
              COALESCE(o.pay_amount, o.order_amount, 0)
            ) AS total_revenue
          FROM orders o
          WHERE DATE(o.created_at) BETWEEN :from_date AND :to_date
            AND (:plat = '' OR o.platform = :plat)
            AND (:shop = '' OR o.shop_id = :shop)
          GROUP BY o.platform, o.shop_id
        ),
        ship_cost_shop AS (
          SELECT
            sr.platform,
            sr.shop_id,
            SUM(COALESCE(sr.cost_estimated, 0)) AS total_shipping_cost
          FROM shipping_records sr
          WHERE DATE(sr.created_at) BETWEEN :from_date AND :to_date
            AND (:plat = '' OR sr.platform = :plat)
            AND (:shop = '' OR sr.shop_id = :shop)
          GROUP BY sr.platform, sr.shop_id
        ),
        shop_dim AS (
          SELECT DISTINCT platform, shop_id FROM order_revenue_shop
          UNION
          SELECT DISTINCT platform, shop_id FROM order_line_cost_shop
          UNION
          SELECT DISTINCT platform, shop_id FROM ship_cost_shop
        )
        SELECT
          sd.platform,
          sd.shop_id,
          COALESCE(orev.total_revenue, 0)       AS revenue,
          COALESCE(oc.total_purchase_cost, 0)   AS purchase_cost,
          COALESCE(sc.total_shipping_cost, 0)   AS shipping_cost
        FROM shop_dim sd
        LEFT JOIN order_revenue_shop   orev
          ON orev.platform = sd.platform AND orev.shop_id = sd.shop_id
        LEFT JOIN order_line_cost_shop oc
          ON oc.platform   = sd.platform AND oc.shop_id   = sd.shop_id
        LEFT JOIN ship_cost_shop       sc
          ON sc.platform   = sd.platform AND sc.shop_id   = sd.shop_id
        ORDER BY sd.platform, sd.shop_id
        """
    )

    result = await session.execute(
        sql,
        {
            "from_date": from_dt,
            "to_date": to_dt,
            "plat": plat,
            "shop": shop,
        },
    )
    rows = result.mappings().all()

    items: List[FinanceShopRow] = []
    for row in rows:
        platform_val = str(row["platform"])
        shop_val = str(row["shop_id"])

        revenue = Decimal(str(row["revenue"] or 0))
        purchase_cost = Decimal(str(row["purchase_cost"] or 0))
        shipping_cost = Decimal(str(row["shipping_cost"] or 0))

        gross_profit = revenue - purchase_cost - shipping_cost

        if revenue > 0:
            gross_margin = (gross_profit / revenue).quantize(Decimal("0.0001"))
            fulfillment_ratio = (shipping_cost / revenue).quantize(
                Decimal("0.0001"),
            )
        else:
            gross_margin = None
            fulfillment_ratio = None

        items.append(
            FinanceShopRow(
                platform=platform_val,
                shop_id=shop_val,
                revenue=revenue,
                purchase_cost=purchase_cost,
                shipping_cost=shipping_cost,
                gross_profit=gross_profit,
                gross_margin=gross_margin,
                fulfillment_ratio=fulfillment_ratio,
            )
        )

    return items


# ---------------------------------------------------------------------------
# /finance/sku  — SKU 毛利榜（不含运费）
# ---------------------------------------------------------------------------


@router.get(
    "/sku",
    response_model=List[FinanceSkuRow],
    summary="SKU 毛利榜（不含运费，基于平均进货价）",
)
async def finance_by_sku(
    session: AsyncSession = Depends(get_session),
    current_user: Any = Depends(get_current_user),
    from_date: Optional[str] = Query(
        None,
        description="起始日期（YYYY-MM-DD，含）。默认=今天往前 6 天。",
    ),
    to_date: Optional[str] = Query(
        None,
        description="结束日期（YYYY-MM-DD，含）。默认=今天。",
    ),
    platform: Optional[str] = Query(
        None,
        description="按平台过滤，例如 PDD / JD（可选）",
    ),
) -> List[FinanceSkuRow]:
    """
    SKU 毛利榜（粗粒度版本）：

    - 维度：item_id（辅以 sku_id / title）
    - 收入：SUM(order_items.amount)，若 amount 为空则退回 qty * price
    - 商品成本：avg_unit_cost(item_id) × SUM(order_items.qty)
        * avg_unit_cost = purchase_order_lines.line_amount
                          / (qty_ordered * units_per_case)
    - 不含运费：暂不分摊 shipping_records，专注商品毛利。
    """
    from_dt = _parse_date_param(from_date)
    to_dt = _parse_date_param(to_date)

    if from_dt is None or to_dt is None:
        sql_default = text("SELECT current_date AS today")
        today_row = (await session.execute(sql_default)).mappings().first()
        today: date = today_row["today"]  # type: ignore[assignment]
        to_dt = today
        from_dt = date.fromordinal(today.toordinal() - 6)

    plat = (platform or "").strip().upper()

    sql = text(
        """
        WITH item_cost AS (
          SELECT
            pol.item_id,
            COALESCE(SUM(COALESCE(pol.line_amount, 0)), 0) AS total_amount,
            COALESCE(SUM(pol.qty_ordered * COALESCE(pol.units_per_case, 1)), 0) AS total_units
          FROM purchase_orders po
          JOIN purchase_order_lines pol ON pol.po_id = po.id
          GROUP BY pol.item_id
        ),
        item_avg_cost AS (
          SELECT
            item_id,
            CASE
              WHEN total_units > 0 THEN total_amount / total_units
              ELSE NULL
            END AS avg_unit_cost
          FROM item_cost
        ),
        sku_agg AS (
          SELECT
            oi.item_id,
            MAX(oi.sku_id)           AS sku_id,
            MAX(oi.title)            AS title,
            COALESCE(SUM(oi.qty), 0) AS qty_sold,
            SUM(
              COALESCE(
                oi.amount,
                COALESCE(oi.qty, 0) * COALESCE(oi.price, 0)
              )
            ) AS revenue,
            SUM(
              COALESCE(oi.qty, 0) * COALESCE(iac.avg_unit_cost, 0)
            ) AS purchase_cost
          FROM orders o
          JOIN order_items oi ON oi.order_id = o.id
          LEFT JOIN item_avg_cost iac ON iac.item_id = oi.item_id
          WHERE DATE(o.created_at) BETWEEN :from_date AND :to_date
            AND (:plat = '' OR o.platform = :plat)
          GROUP BY oi.item_id
        )
        SELECT
          item_id,
          sku_id,
          title,
          qty_sold,
          COALESCE(revenue, 0)        AS revenue,
          COALESCE(purchase_cost, 0)  AS purchase_cost
        FROM sku_agg
        WHERE qty_sold > 0
        ORDER BY revenue DESC
        """
    )

    result = await session.execute(
        sql,
        {
            "from_date": from_dt,
            "to_date": to_dt,
            "plat": plat,
        },
    )
    rows = result.mappings().all()

    items: List[FinanceSkuRow] = []
    for row in rows:
        item_id = int(row["item_id"])
        sku_id = row.get("sku_id")
        title = row.get("title")

        qty_sold = int(row["qty_sold"] or 0)
        revenue = Decimal(str(row["revenue"] or 0))
        purchase_cost = Decimal(str(row["purchase_cost"] or 0))

        gross_profit = revenue - purchase_cost

        if revenue > 0:
            gross_margin = (gross_profit / revenue).quantize(Decimal("0.0001"))
        else:
            gross_margin = None

        items.append(
            FinanceSkuRow(
                item_id=item_id,
                sku_id=sku_id,
                title=title,
                qty_sold=qty_sold,
                revenue=revenue,
                purchase_cost=purchase_cost,
                gross_profit=gross_profit,
                gross_margin=gross_margin,
            )
        )

    return items


# ---------------------------------------------------------------------------
# /finance/order-unit — 客单价 & 贡献度分析
# ---------------------------------------------------------------------------


@router.get(
    "/order-unit",
    summary="客单价 & 贡献度分析（按订单维度）",
)
async def finance_order_unit(
    session: AsyncSession = Depends(get_session),
    current_user: Any = Depends(get_current_user),
    from_date: Optional[str] = Query(
        None,
        description="起始日期（YYYY-MM-DD，含）。默认=今天往前 6 天。",
    ),
    to_date: Optional[str] = Query(
        None,
        description="结束日期（YYYY-MM-DD，含）。默认=今天。",
    ),
    platform: Optional[str] = Query(
        None,
        description="按平台过滤，例如 PDD / JD（可选）",
    ),
    shop_id: Optional[str] = Query(
        None,
        description="按店铺 ID 过滤（可选）",
    ),
) -> dict:
    """
    客单价 & 贡献度分析：

    - 每一条记录 = 一笔订单（order_value = pay_amount 或 order_amount）
    - summary：订单数 / 总收入 / 平均客单价 / 中位客单价
    - contribution_curve：前 20%/40%/60%/80%/100% 订单贡献的收入占比
    - top_orders：按金额从大到小列出前 N 笔订单
    """
    from_dt = _parse_date_param(from_date)
    to_dt = _parse_date_param(to_date)

    if from_dt is None or to_dt is None:
        sql_default = text("SELECT current_date AS today")
        today_row = (await session.execute(sql_default)).mappings().first()
        today: date = today_row["today"]  # type: ignore[assignment]
        to_dt = today
        from_dt = date.fromordinal(today.toordinal() - 6)

    plat = (platform or "").strip().upper()
    shop = (shop_id or "").strip()

    sql = text(
        """
        SELECT
          o.id           AS order_id,
          o.platform     AS platform,
          o.shop_id      AS shop_id,
          o.ext_order_no AS ext_order_no,
          COALESCE(o.pay_amount, o.order_amount, 0) AS order_value,
          o.created_at   AS created_at
        FROM orders o
        WHERE DATE(o.created_at) BETWEEN :from_date AND :to_date
          AND (:plat = '' OR o.platform = :plat)
          AND (:shop = '' OR o.shop_id = :shop)
        """
    )

    result = await session.execute(
        sql,
        {
            "from_date": from_dt,
            "to_date": to_dt,
            "plat": plat,
            "shop": shop,
        },
    )
    rows = result.mappings().all()

    # 没有订单时，直接返回空 summary
    if not rows:
        empty_summary = OrderUnitSummary(
            order_count=0,
            revenue=Decimal("0"),
            avg_order_value=None,
            median_order_value=None,
        )
        return {
            "summary": empty_summary.model_dump(),
            "contribution_curve": [],
            "top_orders": [],
        }

    # 提取 order_value 列表，做排序与统计
    values: list[Decimal] = []
    base_rows: list[OrderUnitRow] = []

    for r in rows:
        order_value = Decimal(str(r["order_value"] or 0))
        values.append(order_value)
        base_rows.append(
            OrderUnitRow(
                order_id=int(r["order_id"]),
                platform=str(r["platform"]),
                shop_id=str(r["shop_id"]),
                ext_order_no=str(r["ext_order_no"]),
                order_value=order_value,
                created_at=r["created_at"].isoformat(),
            )
        )

    order_count = len(values)
    total_revenue = sum(values, Decimal("0"))

    # 平均客单价
    if order_count > 0:
        avg_order_value = (total_revenue / order_count).quantize(Decimal("0.01"))
    else:
        avg_order_value = None

    # 中位数
    values_sorted = sorted(values)
    mid = order_count // 2
    if order_count % 2 == 1:
        median_order_value = values_sorted[mid]
    else:
        median_order_value = (values_sorted[mid - 1] + values_sorted[mid]) / 2
    median_order_value = median_order_value.quantize(Decimal("0.01"))

    summary = OrderUnitSummary(
        order_count=order_count,
        revenue=total_revenue,
        avg_order_value=avg_order_value,
        median_order_value=median_order_value,
    )

    # 贡献度曲线：前 20%/40%/60%/80%/100% 订单贡献的收入占比
    # 按订单金额从大到小排序
    rows_sorted = sorted(base_rows, key=lambda x: x.order_value, reverse=True)
    cum_values: list[Decimal] = []
    running = Decimal("0")
    for r in rows_sorted:
        running += r.order_value
        cum_values.append(running)

    buckets = [0.2, 0.4, 0.6, 0.8, 1.0]
    contribution: list[OrderUnitContributionPoint] = []

    for p in buckets:
        idx = max(0, min(order_count - 1, int(order_count * p) - 1))
        revenue_upto = cum_values[idx]
        percent_rev = float((revenue_upto / total_revenue) if total_revenue > 0 else 0)
        contribution.append(
            OrderUnitContributionPoint(
                percent_orders=float(p),
                percent_revenue=percent_rev,
            )
        )

    # top_orders：取前 50 笔大额订单
    top_n = min(50, order_count)
    top_orders = rows_sorted[:top_n]

    return {
        "summary": summary.model_dump(),
        "contribution_curve": [pt.model_dump() for pt in contribution],
        "top_orders": [o.model_dump() for o in top_orders],
    }
