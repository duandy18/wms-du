# app/services/routing_candidates.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.store_service import StoreService


@dataclass(frozen=True)
class CandidateResolveResult:
    store_id: int
    platform: str
    shop_id: str
    province: Optional[str]

    # ✅ 你当前世界观：不做自动 fallback 扩候选集
    route_mode: str  # 固定 STRICT_TOP
    candidate_warehouse_ids: List[int]  # ordered & de-duplicated
    candidate_reason: str  # PROVINCE_ROUTE_MATCH / NO_PROVINCE_ROUTE_MATCH
    fallback_used: bool  # 永远 False（人工干预不属于事实层）


def _dedupe_keep_order(xs: Sequence[int]) -> List[int]:
    seen: set[int] = set()
    out: List[int] = []
    for x in xs:
        try:
            v = int(x)
        except Exception:
            continue
        if v <= 0:
            continue
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


async def _get_or_create_store_id(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
) -> int:
    """
    store 是路由世界观的入口：不存在则 ensure_store（幂等）。
    注意：不再消费 stores.route_mode（避免 FALLBACK 扩候选集引入复杂性）。
    """
    plat = str(platform or "").upper().strip()
    sid = str(shop_id or "").strip()

    row = (
        await session.execute(
            text(
                """
                SELECT id
                  FROM stores
                 WHERE platform = :p
                   AND shop_id  = :s
                 LIMIT 1
                """
            ),
            {"p": plat, "s": sid},
        )
    ).first()

    if row:
        return int(row[0])

    # ✅ 不存在则建档（与既有行为兼容）
    store_id = await StoreService.ensure_store(
        session,
        platform=plat,
        shop_id=sid,
        name=f"{plat}-{sid}",
    )
    return int(store_id)


async def resolve_candidate_warehouses_for_store(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    province: Optional[str],
) -> CandidateResolveResult:
    """
    ✅ 极简候选集解析器（收敛版）

    你的业务模型：
    - 自动归属仓（唯一）：province → store_province_routes 命中
    - 不做自动 fallback（库存不足交给人工改派/退单）

    因此：
    - 候选集只来自 store_province_routes（且要求 active）
    - 未命中 → candidate_warehouse_ids=[]
    """
    plat = str(platform or "").upper().strip()
    sid = str(shop_id or "").strip()
    prov = (province or "").strip() or None

    store_id = await _get_or_create_store_id(session, platform=plat, shop_id=sid)

    prov_ids: List[int] = []
    if prov:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT r.warehouse_id
                      FROM store_province_routes r
                      LEFT JOIN warehouses w ON w.id = r.warehouse_id
                     WHERE r.store_id = :sid
                       AND r.province = :prov
                       AND COALESCE(r.active, TRUE) = TRUE
                       AND COALESCE(w.active, TRUE) = TRUE
                     ORDER BY r.priority ASC, r.id ASC
                    """
                ),
                {"sid": store_id, "prov": prov},
            )
        ).fetchall()

        prov_ids = _dedupe_keep_order([int(x[0]) for x in rows])

    if prov_ids:
        return CandidateResolveResult(
            store_id=store_id,
            platform=plat,
            shop_id=sid,
            province=prov,
            route_mode="STRICT_TOP",
            candidate_warehouse_ids=prov_ids,
            candidate_reason="PROVINCE_ROUTE_MATCH",
            fallback_used=False,
        )

    return CandidateResolveResult(
        store_id=store_id,
        platform=plat,
        shop_id=sid,
        province=prov,
        route_mode="STRICT_TOP",
        candidate_warehouse_ids=[],
        candidate_reason="NO_PROVINCE_ROUTE_MATCH",
        fallback_used=False,
    )


__all__ = ["CandidateResolveResult", "resolve_candidate_warehouses_for_store"]
