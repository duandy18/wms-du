# app/shipping_assist/quote/recommend.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.shipping_assist.quote.calc_quote import calc_quote
from app.shipping_assist.quote.types import Dest


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
    Template-based 推荐逻辑（运行态终态）：

    - 只允许基于 warehouse × provider binding 的 active_template_id 推荐
    - 不再保留 provider 维度静态模板池 fallback

    核心原则：
    - 运行态推荐只认 binding.active_template_id
    - recommend 查询阶段不再要求模板 status='active'
    - 只过滤已 archived 模板；模板完整性在 binding 阶段保障
    - 未来生效（effective_from > now）的 binding 不参与当前推荐
    """
    if warehouse_id is None:
        raise ValueError("warehouse_id required for recommend")

    results: List[Dict[str, Any]] = []

    # =============================
    # 1. 运行态推荐：binding → active_template_id → calc
    # =============================
    if provider_ids:
        sql = text(
            """
            SELECT
              sp.id AS provider_id,
              sp.shipping_provider_code AS shipping_provider_code,
              sp.name AS shipping_provider_name,
              wsp.active_template_id,
              tpl.name AS template_name
            FROM warehouse_shipping_providers AS wsp
            JOIN shipping_providers AS sp
              ON sp.id = wsp.shipping_provider_id
            JOIN shipping_provider_pricing_templates AS tpl
              ON tpl.id = wsp.active_template_id
            WHERE wsp.warehouse_id = :wid
              AND wsp.active = true
              AND sp.active = true
              AND wsp.active_template_id IS NOT NULL
              AND tpl.archived_at IS NULL
              AND (wsp.effective_from IS NULL OR wsp.effective_from <= now())
              AND sp.id = ANY(:pids)
            ORDER BY wsp.priority ASC, sp.priority ASC, sp.id ASC
            """
        )
        rows = db.execute(
            sql,
            {"wid": int(warehouse_id), "pids": [int(x) for x in provider_ids]},
        ).mappings().all()
    else:
        sql = text(
            """
            SELECT
              sp.id AS provider_id,
              sp.shipping_provider_code AS shipping_provider_code,
              sp.name AS shipping_provider_name,
              wsp.active_template_id,
              tpl.name AS template_name
            FROM warehouse_shipping_providers AS wsp
            JOIN shipping_providers AS sp
              ON sp.id = wsp.shipping_provider_id
            JOIN shipping_provider_pricing_templates AS tpl
              ON tpl.id = wsp.active_template_id
            WHERE wsp.warehouse_id = :wid
              AND wsp.active = true
              AND sp.active = true
              AND wsp.active_template_id IS NOT NULL
              AND tpl.archived_at IS NULL
              AND (wsp.effective_from IS NULL OR wsp.effective_from <= now())
            ORDER BY wsp.priority ASC, sp.priority ASC, sp.id ASC
            """
        )
        rows = db.execute(sql, {"wid": int(warehouse_id)}).mappings().all()

    if not rows:
        return {"ok": True, "recommended_template_id": None, "quotes": []}

    for row in rows:
        template_id = int(row["active_template_id"])
        try:
            r = calc_quote(
                db=db,
                template_id=template_id,
                warehouse_id=int(warehouse_id),
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

        results.append(
            {
                "provider_id": int(row["provider_id"]),
                "shipping_provider_code": row.get("shipping_provider_code"),
                "shipping_provider_name": str(row["shipping_provider_name"]),
                "template_id": template_id,
                "template_name": row.get("template_name"),
                "total_amount": float(r["total_amount"]),
                "currency": r.get("currency"),
                "quote_status": r.get("quote_status"),
                "reasons": r.get("reasons") or [],
                "weight": r.get("weight"),
                "destination_group": r.get("destination_group"),
                "pricing_matrix": r.get("pricing_matrix"),
                "breakdown": r.get("breakdown"),
            }
        )

    # =============================
    # 2. 排序 & 返回
    # =============================
    results.sort(
        key=lambda x: (
            float(x["total_amount"]),
            str(x.get("shipping_provider_code") or ""),
        )
    )

    if max_results and len(results) > max_results:
        results = results[:max_results]

    recommended_template_id = results[0]["template_id"] if results else None

    return {
        "ok": True,
        "recommended_template_id": recommended_template_id,
        "quotes": results,
    }
