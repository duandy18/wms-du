# app/services/platform_sku_query/_common.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.platform_sku_binding import PlatformSkuBinding
from app.models.platform_sku_mirror import PlatformSkuMirror


@dataclass(frozen=True)
class MirrorFirstPage:
    mirror_total: int
    mirror_rows: list[PlatformSkuMirror]
    mirror_keys_in_page: set[tuple[str, int, str]]

    bindings_only_total: int
    bindings_only_rows: list[tuple[str, int, str]]  # (platform, store_id, platform_sku_id)


def _count(db: Session, stmt) -> int:
    return int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)


def _apply_order_by(stmt, order_by):
    """
    允许调用方传：
    - 单个 order_by 表达式（InstrumentedAttribute / ClauseElement）
    - tuple/list 的多个表达式（常见： (col1, col2) ）
    """
    if isinstance(order_by, (tuple, list)):
        return stmt.order_by(*order_by)
    return stmt.order_by(order_by)


def build_mirror_base(
    *,
    store_id: int | None,
    platform_upper: str | None,
    q: str | None,
):
    stmt = select(PlatformSkuMirror)

    if store_id is not None:
        stmt = stmt.where(PlatformSkuMirror.store_id == int(store_id))
    if platform_upper:
        stmt = stmt.where(func.upper(PlatformSkuMirror.platform) == platform_upper)

    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            PlatformSkuMirror.platform_sku_id.ilike(like)
            | PlatformSkuMirror.sku_name.ilike(like)
            | PlatformSkuMirror.spec.ilike(like)
        )

    return stmt


def build_bindings_only_base(
    *,
    store_id: int | None,
    platform_upper: str | None,
    q: str | None,
):
    stmt = (
        select(
            PlatformSkuBinding.platform,
            PlatformSkuBinding.store_id,
            PlatformSkuBinding.platform_sku_id,
        )
        .distinct()
    )

    if store_id is not None:
        stmt = stmt.where(PlatformSkuBinding.store_id == int(store_id))
    if platform_upper:
        stmt = stmt.where(func.upper(PlatformSkuBinding.platform) == platform_upper)
    if q:
        stmt = stmt.where(PlatformSkuBinding.platform_sku_id.ilike(f"%{q}%"))

    # bindings-only = bindings distinct key 里存在，但 mirror 不存在的 key
    mirror_exists = (
        select(1)
        .select_from(PlatformSkuMirror)
        .where(
            PlatformSkuMirror.store_id == PlatformSkuBinding.store_id,
            PlatformSkuMirror.platform == PlatformSkuBinding.platform,
            PlatformSkuMirror.platform_sku_id == PlatformSkuBinding.platform_sku_id,
        )
        .limit(1)
    )
    stmt = stmt.where(~mirror_exists.exists())
    return stmt


def fetch_mirror_first_page(
    db: Session,
    *,
    mirror_base,
    bindings_only_base,
    limit: int,
    offset: int,
    mirror_order_by,
    bindings_only_order_by,
) -> MirrorFirstPage:
    mirror_total = _count(db, mirror_base)

    mirror_offset = offset if offset < mirror_total else mirror_total
    mirror_limit = 0
    if offset < mirror_total:
        mirror_limit = min(limit, mirror_total - offset)

    mirror_rows: list[PlatformSkuMirror] = []
    if mirror_limit > 0:
        stmt = _apply_order_by(mirror_base, mirror_order_by).limit(mirror_limit).offset(mirror_offset)
        mirror_rows = db.scalars(stmt).all()

    mirror_keys_in_page = {(m.platform, int(m.store_id), m.platform_sku_id) for m in mirror_rows}

    bindings_only_total = _count(db, bindings_only_base)

    if offset >= mirror_total:
        bindings_only_offset = offset - mirror_total
        bindings_only_limit = limit
    else:
        bindings_only_offset = 0
        bindings_only_limit = max(0, limit - len(mirror_rows))

    bindings_only_rows: list[tuple[str, int, str]] = []
    if bindings_only_limit > 0 and bindings_only_total > 0:
        stmt2 = _apply_order_by(bindings_only_base, bindings_only_order_by).limit(bindings_only_limit).offset(bindings_only_offset)
        rows = db.execute(stmt2).all()
        # row 可能是 Row(...)，统一拆成 tuple
        bindings_only_rows = [(str(r[0]), int(r[1]), str(r[2])) for r in rows]

    return MirrorFirstPage(
        mirror_total=mirror_total,
        mirror_rows=mirror_rows,
        mirror_keys_in_page=mirror_keys_in_page,
        bindings_only_total=bindings_only_total,
        bindings_only_rows=bindings_only_rows,
    )


def load_current_bindings_map(
    db: Session,
    *,
    store_id: int | None,
    platform_upper: str | None,
) -> dict[tuple[str, int, str], PlatformSkuBinding]:
    stmt = select(PlatformSkuBinding).where(PlatformSkuBinding.effective_to.is_(None))
    if store_id is not None:
        stmt = stmt.where(PlatformSkuBinding.store_id == int(store_id))
    if platform_upper:
        stmt = stmt.where(func.upper(PlatformSkuBinding.platform) == platform_upper)

    out: dict[tuple[str, int, str], PlatformSkuBinding] = {}
    for b in db.scalars(stmt).all():
        out[(b.platform, int(b.store_id), b.platform_sku_id)] = b
    return out


def uniq_ints(xs: Iterable[int]) -> list[int]:
    # 稳定去重（保持排序可预测）
    return sorted(set(int(x) for x in xs))
