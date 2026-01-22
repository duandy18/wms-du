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
    route_mode: str  # STRICT_TOP / FALLBACK / ...
    candidate_warehouse_ids: List[int]  # ordered & de-duplicated
    candidate_reason: str  # PROVINCE_ROUTE_MATCH / FALLBACK_TO_BINDINGS / NO_PROVINCE_ROUTE_MATCH / NO_WAREHOUSE_BOUND
    fallback_used: bool


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


async def _get_store_id_and_mode(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
) -> tuple[int, str]:
    """
    store 是路由世界观的事实入口：不存在则自动建档（幂等）。
    """
    plat = str(platform or "").upper().strip()
    sid = str(shop_id or "").strip()

    row = (
        await session.execute(
            text(
                """
                SELECT id, COALESCE(route_mode, 'FALLBACK') AS route_mode
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
        return int(row[0]), str(row[1] or "FALLBACK").upper()

    # ✅ 不存在则建档（与 ship_prepare 对齐）
    store_id = await StoreService.ensure_store(
        session,
        platform=plat,
        shop_id=sid,
        name=f"{plat}-{sid}",
    )

    # 新建店默认 route_mode 视为 FALLBACK（保持历史行为）
    return int(store_id), "FALLBACK"


async def resolve_candidate_warehouses_for_store(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    province: Optional[str],
) -> CandidateResolveResult:
    """
    ✅ 统一候选集解析器（Phase 4.x 选仓世界观）

    候选集 = store_province_routes 命中集合（裁剪器）
    无命中时：
      - route_mode=FALLBACK → 候选集扩大到 store_warehouse 绑定集合（排序偏好）
      - route_mode=STRICT_TOP → 候选集为空

    注意：
      - store 不存在会自动 ensure_store（幂等建档），避免“隐式默认仓”又不让建档的矛盾
    """
    plat = str(platform or "").upper().strip()
    sid = str(shop_id or "").strip()
    prov = (province or "").strip() or None

    store_id, route_mode = await _get_store_id_and_mode(session, platform=plat, shop_id=sid)

    # 1) 省级路由命中候选集（裁剪器）
    prov_ids: List[int] = []
    if prov:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT
                      r.warehouse_id
                    FROM store_province_routes r
                    JOIN store_warehouse sw
                      ON sw.store_id = r.store_id
                     AND sw.warehouse_id = r.warehouse_id
                    LEFT JOIN warehouses w
                      ON w.id = r.warehouse_id
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
            route_mode=route_mode,
            candidate_warehouse_ids=prov_ids,
            candidate_reason="PROVINCE_ROUTE_MATCH",
            fallback_used=False,
        )

    # 2) 无省路由命中（或 province 缺失）→ route_mode 决定是否允许扩大候选集
    if route_mode != "FALLBACK":
        return CandidateResolveResult(
            store_id=store_id,
            platform=plat,
            shop_id=sid,
            province=prov,
            route_mode=route_mode,
            candidate_warehouse_ids=[],
            candidate_reason="NO_PROVINCE_ROUTE_MATCH",
            fallback_used=False,
        )

    # FALLBACK：扩大到 store_warehouse 绑定集合（排序偏好）
    rows2 = (
        await session.execute(
            text(
                """
                SELECT sw.warehouse_id
                  FROM store_warehouse sw
                  LEFT JOIN warehouses w ON w.id = sw.warehouse_id
                 WHERE sw.store_id = :sid
                   AND COALESCE(w.active, TRUE) = TRUE
                 ORDER BY
                   COALESCE(sw.is_top, FALSE) DESC,
                   COALESCE(sw.is_default, FALSE) DESC,
                   COALESCE(sw.priority, 100) ASC,
                   sw.warehouse_id ASC
                """
            ),
            {"sid": store_id},
        )
    ).fetchall()

    bind_ids = _dedupe_keep_order([int(x[0]) for x in rows2])
    if not bind_ids:
        return CandidateResolveResult(
            store_id=store_id,
            platform=plat,
            shop_id=sid,
            province=prov,
            route_mode=route_mode,
            candidate_warehouse_ids=[],
            candidate_reason="NO_WAREHOUSE_BOUND",
            fallback_used=True,
        )

    return CandidateResolveResult(
        store_id=store_id,
        platform=plat,
        shop_id=sid,
        province=prov,
        route_mode=route_mode,
        candidate_warehouse_ids=bind_ids,
        candidate_reason="FALLBACK_TO_BINDINGS",
        fallback_used=True,
    )


__all__ = ["CandidateResolveResult", "resolve_candidate_warehouses_for_store"]
