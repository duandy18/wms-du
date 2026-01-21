# app/services/shipping_quote/recommend.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.shipping_provider import ShippingProvider
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme

from .calc import _scheme_is_effective, calc_quote
from .types import Dest, _utcnow


def recommend_quotes(
    db: Session,
    provider_ids: Optional[List[int]],
    dest: Dest,
    real_weight_kg: float,
    dims_cm: Optional[Tuple[float, float, float]],
    flags: Optional[List[str]],
    max_results: int = 10,
    warehouse_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    返回：按 total_amount 升序的推荐列表（每个 provider 选最便宜的 effective scheme）。

    Phase 3（严格，无兼容）规则：
    - 只要提供 warehouse_id：
      1) 候选承运商必须来自 warehouse_shipping_providers（wsp.active=true 且 sp.active=true）
         - 如果同时提供 provider_ids：取交集（sp.id in provider_ids）
         - 若该仓无可用承运商，则返回空 quotes（不回退全局）
      2) 候选方案必须来自 shipping_provider_pricing_scheme_warehouses
         - spsw.warehouse_id = warehouse_id AND spsw.active=true
         - scheme.active=true 且 effective
         - 不允许 fallback 到“该 provider 的全局方案”
    - 若未提供 warehouse_id：
      - 兼容入口：provider_ids（若给）或全局 active providers
      - scheme 候选集为 provider 下所有 active+effective schemes
    """
    now = _utcnow()

    providers: List[ShippingProvider] = []

    if warehouse_id is not None:
        # ✅ Phase 3：仓库边界（候选集来自事实绑定，不回退全局）
        if provider_ids:
            sql = text(
                """
                SELECT
                  sp.id,
                  sp.name,
                  sp.code,
                  sp.active,
                  sp.priority,
                  sp.pricing_model,
                  sp.region_rules
                FROM warehouse_shipping_providers AS wsp
                JOIN shipping_providers AS sp
                  ON sp.id = wsp.shipping_provider_id
                WHERE wsp.warehouse_id = :wid
                  AND wsp.active = true
                  AND sp.active = true
                  AND sp.id = ANY(:pids)
                ORDER BY wsp.priority ASC, sp.priority ASC, sp.id ASC
                """
            )
            rows = db.execute(sql, {"wid": int(warehouse_id), "pids": [int(x) for x in provider_ids]}).mappings().all()
        else:
            sql = text(
                """
                SELECT
                  sp.id,
                  sp.name,
                  sp.code,
                  sp.active,
                  sp.priority,
                  sp.pricing_model,
                  sp.region_rules
                FROM warehouse_shipping_providers AS wsp
                JOIN shipping_providers AS sp
                  ON sp.id = wsp.shipping_provider_id
                WHERE wsp.warehouse_id = :wid
                  AND wsp.active = true
                  AND sp.active = true
                ORDER BY wsp.priority ASC, sp.priority ASC, sp.id ASC
                """
            )
            rows = db.execute(sql, {"wid": int(warehouse_id)}).mappings().all()

        for r in rows:
            p = ShippingProvider()
            p.id = int(r["id"])
            p.name = str(r["name"])
            p.code = r.get("code")
            p.active = bool(r.get("active", True))
            p.priority = int(r.get("priority") or 0)
            p.pricing_model = r.get("pricing_model")
            p.region_rules = r.get("region_rules")
            providers.append(p)

        # 若该仓无候选承运商：事实优先，直接空（不回退全局）
        if not providers:
            return {"ok": True, "recommended_scheme_id": None, "quotes": []}

    else:
        # 无 warehouse_id：兼容入口（仅用于非仓库场景）
        if provider_ids:
            q = db.query(ShippingProvider).filter(ShippingProvider.active.is_(True))
            q = q.filter(ShippingProvider.id.in_(provider_ids))
            providers = q.order_by(ShippingProvider.priority.asc(), ShippingProvider.id.asc()).all()
        else:
            q = db.query(ShippingProvider).filter(ShippingProvider.active.is_(True))
            providers = q.order_by(ShippingProvider.priority.asc(), ShippingProvider.id.asc()).all()

    results: List[Dict[str, Any]] = []

    for p in providers:
        if warehouse_id is None:
            schemes = (
                db.query(ShippingProviderPricingScheme)
                .filter(ShippingProviderPricingScheme.shipping_provider_id == p.id)
                .filter(ShippingProviderPricingScheme.active.is_(True))
                .order_by(ShippingProviderPricingScheme.id.asc())
                .all()
            )
        else:
            # ✅ Phase 3：严格消费 scheme×warehouse（不允许 fallback）
            sql_schemes = text(
                """
                SELECT sch.*
                FROM shipping_provider_pricing_schemes AS sch
                JOIN shipping_provider_pricing_scheme_warehouses AS spsw
                  ON spsw.scheme_id = sch.id
                WHERE sch.shipping_provider_id = :pid
                  AND sch.active = true
                  AND spsw.warehouse_id = :wid
                  AND spsw.active = true
                ORDER BY sch.id ASC
                """
            )
            schemes = (
                db.query(ShippingProviderPricingScheme)
                .from_statement(sql_schemes)
                .params(pid=int(p.id), wid=int(warehouse_id))
                .all()
            )

        schemes = [sch for sch in schemes if _scheme_is_effective(sch, now)]
        if not schemes:
            continue

        best: Optional[Dict[str, Any]] = None
        for sch in schemes:
            try:
                r = calc_quote(
                    db=db,
                    scheme_id=sch.id,
                    dest=dest,
                    real_weight_kg=real_weight_kg,
                    dims_cm=dims_cm,
                    flags=flags,
                )
            except Exception:
                continue

            if r.get("quote_status") != "OK":
                continue
            if r.get("total_amount") is None:
                continue

            item = {
                "provider_id": p.id,
                "carrier_code": p.code,
                "carrier_name": p.name,
                "scheme_id": sch.id,
                "scheme_name": sch.name,
                "total_amount": float(r["total_amount"]),
                "currency": r.get("currency"),
                "quote_status": r.get("quote_status"),
                "reasons": r.get("reasons") or [],
                "weight": r.get("weight"),
                "zone": r.get("zone"),
                "bracket": r.get("bracket"),
                "breakdown": r.get("breakdown"),
            }

            if best is None or item["total_amount"] < float(best["total_amount"]):
                best = item

        if best is not None:
            results.append(best)

    results.sort(key=lambda x: (float(x["total_amount"]), str(x.get("carrier_code") or "")))
    if max_results and len(results) > max_results:
        results = results[:max_results]

    recommended_scheme_id = results[0]["scheme_id"] if results else None
    return {"ok": True, "recommended_scheme_id": recommended_scheme_id, "quotes": results}
