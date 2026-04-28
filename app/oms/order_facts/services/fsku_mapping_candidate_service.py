from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.oms.order_facts.contracts.fsku_mapping_candidate import (
    FskuMappingCandidateListDataOut,
    FskuMappingCandidateOut,
)


_PLATFORM_TABLES = {
    "pdd": ("oms_pdd_order_mirrors", "oms_pdd_order_mirror_lines"),
    "taobao": ("oms_taobao_order_mirrors", "oms_taobao_order_mirror_lines"),
    "jd": ("oms_jd_order_mirrors", "oms_jd_order_mirror_lines"),
}


def _tables(platform: str) -> tuple[str, str]:
    key = (platform or "").strip().lower()
    if key not in _PLATFORM_TABLES:
        raise ValueError(f"unsupported platform: {platform!r}")
    return _PLATFORM_TABLES[key]


def _fmt(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _mapping_status(*, merchant_code: str | None, binding_id: int | None) -> str:
    if not merchant_code:
        return "missing_merchant_code"
    if binding_id is not None:
        return "bound"
    return "unbound"


def _candidate_out(platform: str, row: Mapping[str, Any]) -> FskuMappingCandidateOut:
    merchant_code = row.get("merchant_code")
    merchant_code_text = str(merchant_code).strip() if merchant_code is not None else None
    if merchant_code_text == "":
        merchant_code_text = None

    binding_id = row.get("binding_id")
    binding_id_int = int(binding_id) if binding_id is not None else None

    return FskuMappingCandidateOut(
        platform=platform,
        mirror_id=int(row["mirror_id"]),
        line_id=int(row["line_id"]),
        collector_order_id=int(row["collector_order_id"]),
        collector_line_id=int(row["collector_line_id"]),
        store_code=str(row["store_code"]),
        collector_store_id=int(row["collector_store_id"]),
        collector_store_name=str(row["collector_store_name"]),
        platform_order_no=str(row["platform_order_no"]),
        merchant_code=merchant_code_text,
        platform_item_id=row.get("platform_item_id"),
        platform_sku_id=row.get("platform_sku_id"),
        title=row.get("title"),
        quantity=str(row.get("quantity") or "0"),
        line_amount=_fmt(row.get("line_amount")),
        is_bound=binding_id_int is not None,
        mapping_status=_mapping_status(
            merchant_code=merchant_code_text,
            binding_id=binding_id_int,
        ),  # type: ignore[arg-type]
        binding_id=binding_id_int,
        fsku_id=int(row["fsku_id"]) if row.get("fsku_id") is not None else None,
        fsku_code=row.get("fsku_code"),
        fsku_name=row.get("fsku_name"),
        fsku_status=row.get("fsku_status"),
        binding_reason=row.get("binding_reason"),
        binding_updated_at=_fmt(row.get("binding_updated_at")),
    )


async def list_fsku_mapping_candidates(
    session: AsyncSession,
    *,
    platform: str,
    store_code: str | None,
    merchant_code: str | None,
    only_unbound: bool,
    limit: int,
    offset: int,
) -> FskuMappingCandidateListDataOut:
    plat = (platform or "").strip().lower()
    mirror_table, line_table = _tables(plat)

    clauses: list[str] = ["1 = 1"]
    params: dict[str, Any] = {
        "platform": plat,
        "limit": int(limit),
        "offset": int(offset),
    }

    if store_code and store_code.strip():
        clauses.append("m.collector_store_code = :store_code")
        params["store_code"] = store_code.strip()

    if merchant_code and merchant_code.strip():
        clauses.append("l.merchant_sku ILIKE :merchant_code_like")
        params["merchant_code_like"] = f"%{merchant_code.strip()}%"

    if only_unbound:
        clauses.append("b.id IS NULL")

    where_sql = " AND ".join(clauses)

    count_row = (
        await session.execute(
            text(
                f"""
                SELECT count(*) AS total
                  FROM {line_table} l
                  JOIN {mirror_table} m ON m.id = l.mirror_id
                  LEFT JOIN merchant_code_fsku_bindings b
                    ON b.platform = :platform
                   AND b.store_code = m.collector_store_code
                   AND b.merchant_code = l.merchant_sku
                  LEFT JOIN fskus f ON f.id = b.fsku_id
                 WHERE {where_sql}
                """
            ),
            params,
        )
    ).mappings().one()

    rows = (
        await session.execute(
            text(
                f"""
                SELECT
                  m.id AS mirror_id,
                  l.id AS line_id,
                  l.collector_order_id,
                  l.collector_line_id,

                  m.collector_store_code AS store_code,
                  m.collector_store_id,
                  m.collector_store_name,

                  l.platform_order_no,
                  l.merchant_sku AS merchant_code,
                  l.platform_item_id,
                  l.platform_sku_id,
                  l.title,
                  l.quantity,
                  l.line_amount,

                  b.id AS binding_id,
                  b.fsku_id,
                  b.reason AS binding_reason,
                  b.updated_at AS binding_updated_at,

                  f.code AS fsku_code,
                  f.name AS fsku_name,
                  f.status AS fsku_status
                FROM {line_table} l
                JOIN {mirror_table} m ON m.id = l.mirror_id
                LEFT JOIN merchant_code_fsku_bindings b
                  ON b.platform = :platform
                 AND b.store_code = m.collector_store_code
                 AND b.merchant_code = l.merchant_sku
                LEFT JOIN fskus f ON f.id = b.fsku_id
                WHERE {where_sql}
                ORDER BY m.last_synced_at DESC, m.id DESC, l.id ASC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    ).mappings().all()

    return FskuMappingCandidateListDataOut(
        items=[_candidate_out(plat, row) for row in rows],
        total=int(count_row["total"]),
        limit=int(limit),
        offset=int(offset),
    )
