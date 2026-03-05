# app/services/zone_guards.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.shipping_provider_zone import ShippingProviderZone


@dataclass(frozen=True)
class ZoneOverlapError(Exception):
    scheme_id: int
    overlapped_provinces: list[str]
    conflict_zone_ids: list[int]

    def __str__(self) -> str:
        prov = "、".join(self.overlapped_provinces[:10])
        more = "" if len(self.overlapped_provinces) <= 10 else "…"
        return (
            f"区域划分冲突：同一收费标准（scheme_id={self.scheme_id}）下省份重复归属。"
            f"冲突省份：{prov}{more}；冲突区域ID：{self.conflict_zone_ids}"
        )


@dataclass(frozen=True)
class ZoneTemplateRequiredError(Exception):
    def __str__(self) -> str:
        return "区域必须绑定重量段模板（segment_template_id 必填），否则无法形成唯一价格表结构。"


def _norm_provinces(provinces: Iterable[str]) -> set[str]:
    out: set[str] = set()
    for p in provinces:
        if p is None:
            continue
        p2 = str(p).strip()
        if not p2:
            continue
        out.add(p2)
    return out


async def assert_zone_template_required(segment_template_id: int | None) -> None:
    if segment_template_id is None:
        raise ZoneTemplateRequiredError()


async def assert_zone_provinces_no_overlap(
    session: AsyncSession,
    *,
    scheme_id: int,
    provinces: Sequence[str],
    exclude_zone_id: int | None = None,
) -> None:
    """
    硬合同：
    - 同一 scheme 下 province_members 不得交叉
    - provinces 必须是“最终全集”（不是增量）
    """
    target = _norm_provinces(provinces)
    if not target:
        return

    stmt = select(ShippingProviderZone.id, ShippingProviderZone.province_members).where(
        ShippingProviderZone.scheme_id == scheme_id
    )
    if exclude_zone_id is not None:
        stmt = stmt.where(ShippingProviderZone.id != exclude_zone_id)

    rows = (await session.execute(stmt)).all()

    overlapped: set[str] = set()
    conflict_zone_ids: set[int] = set()

    for zone_id, province_members in rows:
        other = _norm_provinces(province_members or [])
        inter = target.intersection(other)
        if inter:
            overlapped |= inter
            conflict_zone_ids.add(int(zone_id))

    if overlapped:
        raise ZoneOverlapError(
            scheme_id=scheme_id,
            overlapped_provinces=sorted(overlapped),
            conflict_zone_ids=sorted(conflict_zone_ids),
        )
