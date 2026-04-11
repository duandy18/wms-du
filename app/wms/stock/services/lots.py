# app/wms/stock/services/lots.py
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def normalize_lot_code(code: str | None) -> tuple[str, str]:
    """
    Normalize supplier lot_code for display / tracing.

    Returns:
        (code_raw, code_lookup)

    兼容保留 tuple 形态，避免外部调用方解包时报错；
    当前 code_lookup 与 code_raw 相同，不再存在 lot_code_key。
    """
    s = (str(code) if code is not None else "").strip()
    if not s:
        raise ValueError("lot_code empty")
    return s, s


def _pair_or_null(a: Optional[int], b: Optional[int]) -> tuple[Optional[int], Optional[int]]:
    """
    INTERNAL lot source fields rule:
    - both NULL, or both NOT NULL.
    """
    if a is None and b is None:
        return None, None
    if a is not None and b is not None:
        return int(a), int(b)
    raise ValueError("internal_source_receipt_line_pair_required")


def _normalize_date_value(v: object) -> date | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v

    s = str(v).strip()
    if not s:
        return None

    try:
        return date.fromisoformat(s)
    except ValueError:
        pass

    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _normalize_positive_int(v: object) -> int | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int):
        return int(v) if int(v) > 0 else None

    s = str(v).strip()
    if not s:
        return None

    try:
        n = int(s)
    except ValueError:
        try:
            n = int(Decimal(s))
        except (InvalidOperation, ValueError):
            return None

    return n if n > 0 else None


def _normalize_shelf_life_unit(v: object) -> str | None:
    s = str(v or "").strip().upper()
    if not s:
        return None

    mapping = {
        "DAY": "DAY",
        "DAYS": "DAY",
        "D": "DAY",
        "天": "DAY",
        "日": "DAY",
        "WEEK": "WEEK",
        "WEEKS": "WEEK",
        "W": "WEEK",
        "周": "WEEK",
        "MONTH": "MONTH",
        "MONTHS": "MONTH",
        "M": "MONTH",
        "月": "MONTH",
        "YEAR": "YEAR",
        "YEARS": "YEAR",
        "Y": "YEAR",
        "年": "YEAR",
    }
    return mapping.get(s)


def _add_months(base: date, months: int) -> date:
    month_index = (base.month - 1) + months
    year = base.year + (month_index // 12)
    month = (month_index % 12) + 1
    day = min(base.day, monthrange(year, month)[1])
    return date(year, month, day)


def _add_years(base: date, years: int) -> date:
    year = base.year + years
    day = min(base.day, monthrange(year, base.month)[1])
    return date(year, base.month, day)


def _shift_date_by_shelf_life(
    base: date,
    *,
    shelf_life_value: int | None,
    shelf_life_unit: str | None,
    direction: int,
) -> date | None:
    if shelf_life_value is None or shelf_life_unit is None:
        return None

    step = shelf_life_value if direction >= 0 else -shelf_life_value
    if shelf_life_unit == "DAY":
        return base + timedelta(days=step)
    if shelf_life_unit == "WEEK":
        return base + timedelta(weeks=step)
    if shelf_life_unit == "MONTH":
        return _add_months(base, step)
    if shelf_life_unit == "YEAR":
        return _add_years(base, step)
    return None


async def _load_item_expiry_context(
    session: AsyncSession,
    *,
    item_id: int,
) -> tuple[str, int | None, str | None]:
    row = await session.execute(
        text(
            """
            SELECT
                expiry_policy,
                shelf_life_value,
                shelf_life_unit
              FROM items
             WHERE id = :i
             LIMIT 1
            """
        ),
        {"i": int(item_id)},
    )
    got = row.mappings().first()
    if got is None:
        raise ValueError("item_not_found")

    expiry_policy = str(got["expiry_policy"] or "").strip().upper()
    shelf_life_value = _normalize_positive_int(got["shelf_life_value"])
    shelf_life_unit = _normalize_shelf_life_unit(got["shelf_life_unit"])
    return expiry_policy, shelf_life_value, shelf_life_unit


async def _load_item_expiry_policy(
    session: AsyncSession,
    *,
    item_id: int,
) -> str:
    expiry_policy, _, _ = await _load_item_expiry_context(session, item_id=item_id)
    return expiry_policy


async def _get_supplier_lot_by_production_date(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    production_date: date,
) -> int | None:
    row = await session.execute(
        text(
            """
            SELECT id
              FROM lots
             WHERE warehouse_id = :w
               AND item_id      = :i
               AND lot_code_source = 'SUPPLIER'
               AND production_date = :pd
             ORDER BY id ASC
             LIMIT 1
            """
        ),
        {"w": int(warehouse_id), "i": int(item_id), "pd": production_date},
    )
    got = row.scalar_one_or_none()
    return int(got) if got is not None else None


async def _get_supplier_lot_ids_by_lot_code(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    lot_code: str,
) -> list[int]:
    rows = await session.execute(
        text(
            """
            SELECT id
              FROM lots
             WHERE warehouse_id = :w
               AND item_id      = :i
               AND lot_code_source = 'SUPPLIER'
               AND lot_code = :code
             ORDER BY id ASC
             LIMIT 2
            """
        ),
        {"w": int(warehouse_id), "i": int(item_id), "code": str(lot_code)},
    )
    return [int(r[0]) for r in rows.fetchall()]


async def _patch_lot_expiry_if_null(
    session: AsyncSession,
    *,
    lot_id: int,
    expiry_date: date | None,
) -> None:
    """
    单向补丁：
    - 只允许 NULL -> 值
    - 不允许覆盖已有非空 expiry_date
    """
    if expiry_date is None:
        return

    await session.execute(
        text(
            """
            UPDATE lots
               SET expiry_date = :ed
             WHERE id = :lot_id
               AND expiry_date IS NULL
            """
        ),
        {"lot_id": int(lot_id), "ed": expiry_date},
    )


async def ensure_internal_lot_singleton(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    source_receipt_id: Optional[int] = None,
    source_line_no: Optional[int] = None,
) -> int:
    """
    INTERNAL lot singleton (warehouse_id, item_id):
    - lot_code_source='INTERNAL'
    - lot_code IS NULL
    - UNIQUE (warehouse_id,item_id) WHERE INTERNAL & lot_code IS NULL

    source_receipt_id/source_line_no are optional provenance fields:
    - both NULL, or both NOT NULL
    """
    rid, rln = _pair_or_null(source_receipt_id, source_line_no)

    row0 = await session.execute(
        text(
            """
            SELECT id
              FROM lots
             WHERE warehouse_id = :w
               AND item_id      = :i
               AND lot_code_source = 'INTERNAL'
               AND lot_code IS NULL
             ORDER BY id ASC
             LIMIT 1
            """
        ),
        {"w": int(warehouse_id), "i": int(item_id)},
    )
    got0 = row0.scalar_one_or_none()
    if got0 is not None:
        return int(got0)

    row = await session.execute(
        text(
            """
            INSERT INTO lots(
                warehouse_id,
                item_id,
                lot_code_source,
                lot_code,
                source_receipt_id,
                source_line_no,
                item_lot_source_policy_snapshot,
                item_expiry_policy_snapshot,
                item_derivation_allowed_snapshot,
                item_uom_governance_enabled_snapshot,
                item_shelf_life_value_snapshot,
                item_shelf_life_unit_snapshot
            )
            SELECT
                :w,
                :i,
                'INTERNAL',
                NULL,
                :rid,
                :rln,
                it.lot_source_policy,
                it.expiry_policy,
                it.derivation_allowed,
                it.uom_governance_enabled,
                it.shelf_life_value,
                it.shelf_life_unit
              FROM items it
             WHERE it.id = :i
            ON CONFLICT DO NOTHING
            RETURNING id
            """
        ),
        {"w": int(warehouse_id), "i": int(item_id), "rid": rid, "rln": rln},
    )
    got = row.scalar_one_or_none()
    if got is not None:
        return int(got)

    row2 = await session.execute(
        text(
            """
            SELECT id
              FROM lots
             WHERE warehouse_id = :w
               AND item_id      = :i
               AND lot_code_source = 'INTERNAL'
               AND lot_code IS NULL
             ORDER BY id ASC
             LIMIT 1
            """
        ),
        {"w": int(warehouse_id), "i": int(item_id)},
    )
    got2 = row2.scalar_one_or_none()
    if got2 is None:
        raise RuntimeError("ensure_internal_lot_singleton failed to materialize INTERNAL lot row")
    return int(got2)


async def ensure_lot_full(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    lot_code: str,
    production_date,
    expiry_date,
) -> int:
    """
    SUPPLIER lot 唯一入口。

    当前主链语义：
    - REQUIRED 商品：lot 身份 = (warehouse_id, item_id, production_date)
    - lot_code 只保留为展示 / 输入 / 追溯属性
    - NONE 商品不再创建新的 SUPPLIER lot；只允许回查历史遗留（若仍存在且唯一）
    """
    code_raw, _code_lookup = normalize_lot_code(lot_code)
    pd = _normalize_date_value(production_date)
    ed = _normalize_date_value(expiry_date)
    expiry_policy, shelf_life_value, shelf_life_unit = await _load_item_expiry_context(
        session,
        item_id=int(item_id),
    )

    if expiry_policy == "REQUIRED":
        if ed is None and pd is not None:
            ed = _shift_date_by_shelf_life(
                pd,
                shelf_life_value=shelf_life_value,
                shelf_life_unit=shelf_life_unit,
                direction=1,
            )
        if pd is None and ed is not None:
            pd = _shift_date_by_shelf_life(
                ed,
                shelf_life_value=shelf_life_value,
                shelf_life_unit=shelf_life_unit,
                direction=-1,
            )

    if ed is not None and pd is not None and ed < pd:
        raise ValueError("expiry_date_cannot_be_earlier_than_production_date")

    if expiry_policy == "REQUIRED":
        if pd is None:
            legacy_ids = await _get_supplier_lot_ids_by_lot_code(
                session,
                item_id=int(item_id),
                warehouse_id=int(warehouse_id),
                lot_code=code_raw,
            )
            if len(legacy_ids) == 1:
                lot_id = int(legacy_ids[0])
                await _patch_lot_expiry_if_null(session, lot_id=lot_id, expiry_date=ed)
                return lot_id
            if len(legacy_ids) > 1:
                raise ValueError("supplier_lot_code_ambiguous")
            raise ValueError("production_date_required_for_required_lot")

        existing_by_pd = await _get_supplier_lot_by_production_date(
            session,
            item_id=int(item_id),
            warehouse_id=int(warehouse_id),
            production_date=pd,
        )
        if existing_by_pd is not None:
            lot_id = int(existing_by_pd)
            await _patch_lot_expiry_if_null(session, lot_id=lot_id, expiry_date=ed)
            return lot_id

        if ed is None:
            raise ValueError("expiry_date_required_for_required_lot")

        row = await session.execute(
            text(
                """
                INSERT INTO lots(
                    warehouse_id,
                    item_id,
                    lot_code_source,
                    lot_code,
                    production_date,
                    expiry_date,
                    source_receipt_id,
                    source_line_no,
                    item_lot_source_policy_snapshot,
                    item_expiry_policy_snapshot,
                    item_derivation_allowed_snapshot,
                    item_uom_governance_enabled_snapshot,
                    item_shelf_life_value_snapshot,
                    item_shelf_life_unit_snapshot
                )
                SELECT
                    :w,
                    :i,
                    'SUPPLIER',
                    :code_raw,
                    :pd,
                    :ed,
                    NULL,
                    NULL,
                    it.lot_source_policy,
                    it.expiry_policy,
                    it.derivation_allowed,
                    it.uom_governance_enabled,
                    it.shelf_life_value,
                    it.shelf_life_unit
                  FROM items it
                 WHERE it.id = :i
                ON CONFLICT (warehouse_id, item_id, production_date)
                WHERE lot_code_source = 'SUPPLIER'
                  AND item_expiry_policy_snapshot = 'REQUIRED'
                  AND production_date IS NOT NULL
                DO NOTHING
                RETURNING id
                """
            ),
            {
                "w": int(warehouse_id),
                "i": int(item_id),
                "code_raw": code_raw,
                "pd": pd,
                "ed": ed,
            },
        )
        got = row.scalar_one_or_none()
        if got is not None:
            return int(got)

        existing_by_pd_2 = await _get_supplier_lot_by_production_date(
            session,
            item_id=int(item_id),
            warehouse_id=int(warehouse_id),
            production_date=pd,
        )
        if existing_by_pd_2 is not None:
            lot_id = int(existing_by_pd_2)
            await _patch_lot_expiry_if_null(session, lot_id=lot_id, expiry_date=ed)
            return lot_id

        raise RuntimeError("ensure_lot_full failed to materialize lot row by production_date")

    legacy_ids = await _get_supplier_lot_ids_by_lot_code(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        lot_code=code_raw,
    )
    if len(legacy_ids) == 1:
        return int(legacy_ids[0])
    if len(legacy_ids) > 1:
        raise ValueError("supplier_lot_code_ambiguous")
    raise ValueError("supplier_lot_not_allowed_for_nonrequired_item")


async def ensure_batch_full(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    batch_code: str,
    production_date,
    expiry_date,
) -> int:
    return await ensure_lot_full(
        session,
        item_id=item_id,
        warehouse_id=warehouse_id,
        lot_code=batch_code,
        production_date=production_date,
        expiry_date=expiry_date,
    )


__all__ = [
    "normalize_lot_code",
    "ensure_internal_lot_singleton",
    "ensure_lot_full",
    "ensure_batch_full",
]
