# app/api/routers/stores_order_sim_repo.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _normalize_platform(p: str) -> str:
    s = (p or "").strip().upper()
    if not s:
        raise HTTPException(status_code=500, detail="store.platform 为空：数据异常")
    return s


async def load_store_platform_shop_id(session: AsyncSession, *, store_id: int) -> Tuple[str, str]:
    row = (
        await session.execute(
            text(
                """
                SELECT platform, shop_id
                  FROM stores
                 WHERE id = :sid
                 LIMIT 1
                """
            ),
            {"sid": int(store_id)},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="store not found")
    return _normalize_platform(str(row.get("platform") or "")), str(row.get("shop_id") or "")


async def get_merchant_lines(session: AsyncSession, *, store_id: int) -> List[Dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT
                  row_no,
                  filled_code,
                  title,
                  spec,
                  version,
                  updated_at
                FROM store_order_sim_merchant_lines
                WHERE store_id = :sid
                ORDER BY row_no ASC
                """
            ),
            {"sid": int(store_id)},
        )
    ).mappings().all()

    by_no: Dict[int, Dict[str, Any]] = {int(r["row_no"]): dict(r) for r in rows}
    out: List[Dict[str, Any]] = []
    for i in range(1, 7):
        r = by_no.get(i) or {}
        out.append(
            {
                "row_no": i,
                "filled_code": r.get("filled_code"),
                "title": r.get("title"),
                "spec": r.get("spec"),
                "version": int(r.get("version") or 0),
                "updated_at": r.get("updated_at"),
            }
        )
    return out


async def get_cart_lines(session: AsyncSession, *, store_id: int) -> List[Dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT
                  row_no,
                  checked,
                  qty,
                  province,
                  city,
                  version,
                  updated_at
                FROM store_order_sim_cart
                WHERE store_id = :sid
                ORDER BY row_no ASC
                """
            ),
            {"sid": int(store_id)},
        )
    ).mappings().all()

    by_no: Dict[int, Dict[str, Any]] = {int(r["row_no"]): dict(r) for r in rows}
    out: List[Dict[str, Any]] = []
    for i in range(1, 7):
        r = by_no.get(i) or {}
        out.append(
            {
                "row_no": i,
                "checked": bool(r.get("checked") or False),
                "qty": int(r.get("qty") or 0),
                "province": r.get("province"),
                "city": r.get("city"),
                "version": int(r.get("version") or 0),
                "updated_at": r.get("updated_at"),
            }
        )
    return out


async def upsert_merchant_line(
    session: AsyncSession,
    *,
    store_id: int,
    row_no: int,
    filled_code: Optional[str],
    title: Optional[str],
    spec: Optional[str],
    if_version: Optional[int],
) -> None:
    if if_version is not None:
        cur = (
            await session.execute(
                text(
                    """
                    SELECT version
                      FROM store_order_sim_merchant_lines
                     WHERE store_id=:sid AND row_no=:rn
                     LIMIT 1
                    """
                ),
                {"sid": int(store_id), "rn": int(row_no)},
            )
        ).mappings().first()
        cur_v = int(cur["version"]) if cur and cur.get("version") is not None else 0
        if int(if_version) != cur_v:
            raise HTTPException(
                status_code=409,
                detail=f"版本冲突：row_no={row_no} if_version={if_version} current={cur_v}",
            )

    await session.execute(
        text(
            """
            INSERT INTO store_order_sim_merchant_lines(
              store_id, row_no,
              filled_code, title, spec,
              version, updated_at
            )
            VALUES(
              :sid, :rn,
              :filled_code, :title, :spec,
              1, now()
            )
            ON CONFLICT (store_id, row_no)
            DO UPDATE SET
              filled_code = EXCLUDED.filled_code,
              title       = EXCLUDED.title,
              spec        = EXCLUDED.spec,
              version     = store_order_sim_merchant_lines.version + 1,
              updated_at  = now()
            """
        ),
        {
            "sid": int(store_id),
            "rn": int(row_no),
            "filled_code": None if not (filled_code or "").strip() else str(filled_code).strip(),
            "title": None if title is None else str(title),
            "spec": None if spec is None else str(spec),
        },
    )


async def upsert_cart_line(
    session: AsyncSession,
    *,
    store_id: int,
    row_no: int,
    checked: bool,
    qty: int,
    province: Optional[str],
    city: Optional[str],
    if_version: Optional[int],
) -> None:
    if if_version is not None:
        cur = (
            await session.execute(
                text(
                    """
                    SELECT version
                      FROM store_order_sim_cart
                     WHERE store_id=:sid AND row_no=:rn
                     LIMIT 1
                    """
                ),
                {"sid": int(store_id), "rn": int(row_no)},
            )
        ).mappings().first()
        cur_v = int(cur["version"]) if cur and cur.get("version") is not None else 0
        if int(if_version) != cur_v:
            raise HTTPException(
                status_code=409,
                detail=f"版本冲突：row_no={row_no} if_version={if_version} current={cur_v}",
            )

    q = int(qty or 0)
    if q < 0:
        raise HTTPException(status_code=422, detail=f"qty 不能为负数：row_no={row_no}")

    await session.execute(
        text(
            """
            INSERT INTO store_order_sim_cart(
              store_id, row_no,
              checked, qty, province, city,
              version, updated_at
            )
            VALUES(
              :sid, :rn,
              :checked, :qty, :province, :city,
              1, now()
            )
            ON CONFLICT (store_id, row_no)
            DO UPDATE SET
              checked    = EXCLUDED.checked,
              qty        = EXCLUDED.qty,
              province   = EXCLUDED.province,
              city       = EXCLUDED.city,
              version    = store_order_sim_cart.version + 1,
              updated_at = now()
            """
        ),
        {
            "sid": int(store_id),
            "rn": int(row_no),
            "checked": bool(checked),
            "qty": q,
            "province": None if province is None else str(province),
            "city": None if city is None else str(city),
        },
    )
