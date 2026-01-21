# app/services/metrics_alerts.py
from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.metrics_alerts import AlertItem, AlertsResponse


def _today_utc_date() -> date:
    return datetime.utcnow().date()


def _severity_for_threshold(count: int, threshold: int, *, crit_factor: float = 3.0) -> str:
    if count >= int(threshold * crit_factor):
        return "CRIT"
    if count >= threshold:
        return "WARN"
    return "INFO"


async def _load_outbound_reject_stats(
    session: AsyncSession,
    *,
    day: date,
    platform: str,
    sample_n: int = 3,
) -> Dict[str, Dict[str, object]]:
    """
    返回：
    {
      "SHIP_CONFIRM_TRACKING_DUP": {"count": 12, "sample_refs": ["REF1","REF2",...]},
      ...
    }
    """
    sql = text(
        """
        SELECT
          COALESCE(meta->>'error_code','UNKNOWN') AS error_code,
          COUNT(*) AS n,
          array_agg(ref ORDER BY created_at DESC) AS refs
        FROM audit_events
        WHERE category = 'OUTBOUND'
          AND (meta->>'event') = 'SHIP_CONFIRM_REJECT'
          AND (meta->>'platform') = :platform
          AND (created_at AT TIME ZONE 'utc')::date = :day
        GROUP BY 1
        """
    )
    rows = (await session.execute(sql, {"day": day, "platform": platform})).fetchall()
    out: Dict[str, Dict[str, object]] = {}
    for r in rows:
        code = str(r.error_code or "UNKNOWN")
        n = int(r.n or 0)
        refs = list(r.refs or [])
        out[code] = {"count": n, "sample_refs": refs[: int(sample_n)]}
    return out


async def _load_shipping_quote_reject_stats(
    session: AsyncSession,
    *,
    day: date,
    sample_n: int = 3,
) -> Dict[str, Dict[str, object]]:
    """
    返回同 _load_outbound_reject_stats 的结构。
    """
    sql = text(
        """
        SELECT
          COALESCE(meta->>'error_code','UNKNOWN') AS error_code,
          COUNT(*) AS n,
          array_agg(ref ORDER BY created_at DESC) AS refs
        FROM audit_events
        WHERE category = 'SHIPPING_QUOTE'
          AND (meta->>'event') IN ('QUOTE_CALC_REJECT','QUOTE_RECOMMEND_REJECT')
          AND (created_at AT TIME ZONE 'utc')::date = :day
        GROUP BY 1
        """
    )
    rows = (await session.execute(sql, {"day": day})).fetchall()
    out: Dict[str, Dict[str, object]] = {}
    for r in rows:
        code = str(r.error_code or "UNKNOWN")
        n = int(r.n or 0)
        refs = list(r.refs or [])
        out[code] = {"count": n, "sample_refs": refs[: int(sample_n)]}
    return out


def _rules_outbound() -> List[Tuple[str, int, str, str]]:
    """
    (code, threshold, title, message)
    """
    return [
        ("SHIP_CONFIRM_TRACKING_DUP", 5, "面单号重复", "同一承运商下重复运单号过多，疑似重复扫描/重复确认。"),
        ("SHIP_CONFIRM_ORDER_DUP", 2, "订单重复确认", "同一订单 ref 被重复确认，可能存在重复提交/幂等问题。"),
        ("SHIP_CONFIRM_SCHEME_NOT_AVAILABLE_FOR_WAREHOUSE", 1, "方案不适用该仓", "出库确认命中“方案不适用该仓”，配置可能被误解绑/停用。"),
        ("SHIP_CONFIRM_CARRIER_NOT_ENABLED_FOR_WAREHOUSE", 1, "承运商未在仓启用", "出库确认命中“承运商未在该仓启用”，仓库快递能力配置可能缺失。"),
        ("SHIP_CONFIRM_CARRIER_NOT_AVAILABLE", 1, "承运商不可用", "承运商主数据 inactive 或不存在，需检查主数据。"),
    ]


def _rules_shipping_quote() -> List[Tuple[str, int, str, str]]:
    return [
        ("QUOTE_CALC_NO_MATCHING_ZONE", 10, "区域未覆盖", "算价找不到匹配 Zone，区域覆盖存在缺口。"),
        ("QUOTE_CALC_NO_MATCHING_BRACKET", 10, "重量段未覆盖", "算价找不到匹配 Bracket，重量区间存在缺口。"),
        ("QUOTE_CALC_SCHEME_NOT_EFFECTIVE", 1, "方案未生效", "算价命中“方案未生效”，可能 active=false 或有效期配置错误。"),
        ("QUOTE_CALC_SCHEME_NOT_FOUND", 5, "方案不存在", "算价频繁请求不存在的 scheme_id，可能前端/调用方传参错误。"),
        ("QUOTE_CALC_FAILED", 1, "算价内部异常", "算价出现 500 类错误，需排查服务端异常。"),
        ("QUOTE_RECOMMEND_FAILED", 1, "推荐内部异常", "推荐出现 500 类错误，需排查服务端异常。"),
    ]


async def load_alerts(
    session: AsyncSession,
    *,
    platform: Optional[str],
    day: Optional[date] = None,
    test_mode: bool = False,
    sample_n: int = 3,
) -> AlertsResponse:
    """
    test_mode：
    - 用于验收告警结构（降低阈值，不污染生产阈值）
    - 规则：threshold_eff = 1 if test_mode else threshold

    sample_n：
    - 每个告警返回最近 N 条 ref 样例（用于快速定位）
    """
    d = day or _today_utc_date()
    alerts: List[AlertItem] = []

    def _eff_threshold(th: int) -> int:
        return 1 if test_mode else int(th)

    # OUTBOUND（需要 platform）
    if platform:
        oc = await _load_outbound_reject_stats(session, day=d, platform=platform, sample_n=sample_n)
        for code, threshold, title, msg in _rules_outbound():
            th_eff = _eff_threshold(threshold)
            stat = oc.get(code) or {"count": 0, "sample_refs": []}
            n = int(stat.get("count") or 0)
            if n >= th_eff:
                sev = _severity_for_threshold(n, th_eff, crit_factor=3.0)
                alerts.append(
                    AlertItem(
                        severity=sev,
                        domain="OUTBOUND",
                        code=code,
                        title=title,
                        message=msg,
                        count=n,
                        threshold=th_eff,
                        meta={
                            "platform": platform,
                            "test_mode": test_mode,
                            "sample_refs": stat.get("sample_refs") or [],
                        },
                    )
                )

    # SHIPPING_QUOTE（不区分 platform）
    qc = await _load_shipping_quote_reject_stats(session, day=d, sample_n=sample_n)
    for code, threshold, title, msg in _rules_shipping_quote():
        th_eff = _eff_threshold(threshold)
        stat = qc.get(code) or {"count": 0, "sample_refs": []}
        n = int(stat.get("count") or 0)
        if n >= th_eff:
            sev = _severity_for_threshold(n, th_eff, crit_factor=3.0)
            alerts.append(
                AlertItem(
                    severity=sev,
                    domain="SHIPPING_QUOTE",
                    code=code,
                    title=title,
                    message=msg,
                    count=n,
                    threshold=th_eff,
                    meta={
                        "test_mode": test_mode,
                        "sample_refs": stat.get("sample_refs") or [],
                    },
                )
            )

    # 稳定排序：严重程度优先，其次 count 倒序
    sev_rank = {"CRIT": 0, "WARN": 1, "INFO": 2}
    alerts.sort(key=lambda a: (sev_rank.get(a.severity, 9), -int(a.count), a.domain, a.code))

    return AlertsResponse(day=d, platform=platform, alerts=alerts)
