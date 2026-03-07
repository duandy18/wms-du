# app/api/routers/shipping_provider_pricing_schemes_routes_pricing_matrix_matrix_editor.py
from __future__ import annotations

from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes.schemas import SurchargeOut
from app.api.routers.shipping_provider_pricing_schemes.schemas.matrix_view import (
    MatrixCellOut,
    MatrixGroupOut,
    MatrixGroupProvinceOut,
    MatrixViewDataOut,
    MatrixViewOut,
    MatrixViewSchemeOut,
    MatrixWeightRangeOut,
    PricingMatrixPatchIn,
)
from app.api.routers.shipping_provider_pricing_schemes_mappers import to_surcharge_out
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.models.shipping_provider_destination_group import ShippingProviderDestinationGroup
from app.models.shipping_provider_destination_group_member import (
    ShippingProviderDestinationGroupMember,
)
from app.models.shipping_provider_pricing_matrix import ShippingProviderPricingMatrix
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_surcharge import ShippingProviderSurcharge


def _must_provider_name(sch: ShippingProviderPricingScheme) -> str:
    sp = getattr(sch, "shipping_provider", None)
    name = getattr(sp, "name", None) if sp is not None else None
    if not isinstance(name, str) or not name.strip():
        raise HTTPException(
            status_code=500,
            detail=(
                f"Scheme shipping provider missing/invalid "
                f"(scheme_id={sch.id}, shipping_provider_id={sch.shipping_provider_id})"
            ),
        )
    return name.strip()


def _dec_to_text(v: Decimal) -> str:
    s = format(v, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def _range_key(min_kg: Decimal, max_kg: Optional[Decimal]) -> str:
    return f"{_dec_to_text(min_kg)}:{'inf' if max_kg is None else _dec_to_text(max_kg)}"


def _range_label(min_kg: Decimal, max_kg: Optional[Decimal]) -> str:
    if max_kg is None:
        return f"{_dec_to_text(min_kg)}kg+"
    return f"{_dec_to_text(min_kg)}-{_dec_to_text(max_kg)}kg"


def _load_scheme_or_404(db: Session, scheme_id: int) -> ShippingProviderPricingScheme:
    sch = (
        db.query(ShippingProviderPricingScheme)
        .options(selectinload(ShippingProviderPricingScheme.shipping_provider))
        .filter(ShippingProviderPricingScheme.id == scheme_id)
        .one_or_none()
    )
    if not sch:
        raise HTTPException(status_code=404, detail="Scheme not found")
    return sch


def _load_groups_members_rows(
    db: Session,
    scheme_id: int,
) -> Tuple[
    List[ShippingProviderDestinationGroup],
    Dict[int, List[ShippingProviderDestinationGroupMember]],
    Dict[int, List[ShippingProviderPricingMatrix]],
]:
    groups = (
        db.query(ShippingProviderDestinationGroup)
        .filter(ShippingProviderDestinationGroup.scheme_id == scheme_id)
        .order_by(ShippingProviderDestinationGroup.id.asc())
        .all()
    )
    group_ids = [int(g.id) for g in groups]

    members_by_group: Dict[int, List[ShippingProviderDestinationGroupMember]] = {}
    rows_by_group: Dict[int, List[ShippingProviderPricingMatrix]] = {}

    if not group_ids:
        return groups, members_by_group, rows_by_group

    members = (
        db.query(ShippingProviderDestinationGroupMember)
        .filter(ShippingProviderDestinationGroupMember.group_id.in_(group_ids))
        .order_by(
            ShippingProviderDestinationGroupMember.group_id.asc(),
            ShippingProviderDestinationGroupMember.province_code.asc().nulls_last(),
            ShippingProviderDestinationGroupMember.province_name.asc().nulls_last(),
            ShippingProviderDestinationGroupMember.id.asc(),
        )
        .all()
    )
    for m in members:
        members_by_group.setdefault(int(m.group_id), []).append(m)

    rows = (
        db.query(ShippingProviderPricingMatrix)
        .filter(ShippingProviderPricingMatrix.group_id.in_(group_ids))
        .order_by(
            ShippingProviderPricingMatrix.group_id.asc(),
            ShippingProviderPricingMatrix.min_kg.asc(),
            ShippingProviderPricingMatrix.max_kg.asc().nulls_last(),
            ShippingProviderPricingMatrix.id.asc(),
        )
        .all()
    )
    for row in rows:
        rows_by_group.setdefault(int(row.group_id), []).append(row)

    return groups, members_by_group, rows_by_group


def _build_matrix_view(db: Session, scheme_id: int) -> MatrixViewOut:
    sch = _load_scheme_or_404(db, scheme_id)
    groups, members_by_group, rows_by_group = _load_groups_members_rows(db, scheme_id)

    group_out: List[MatrixGroupOut] = []
    cell_out: List[MatrixCellOut] = []
    range_pairs: List[Tuple[Decimal, Optional[Decimal]]] = []

    for g in groups:
        gid = int(g.id)
        group_key = f"g:{gid}"

        provinces = [
            MatrixGroupProvinceOut(
                id=int(m.id),
                group_id=int(m.group_id),
                province_code=m.province_code,
                province_name=m.province_name,
            )
            for m in members_by_group.get(gid, [])
        ]

        group_out.append(
            MatrixGroupOut(
                id=gid,
                group_key=group_key,
                scheme_id=int(g.scheme_id),
                name=str(g.name),
                active=bool(g.active),
                provinces=provinces,
            )
        )

        for row in rows_by_group.get(gid, []):
            rk = _range_key(row.min_kg, row.max_kg)
            range_pairs.append((row.min_kg, row.max_kg))
            cell_out.append(
                MatrixCellOut(
                    cell_key=f"{group_key}|{rk}",
                    pricing_matrix_id=int(row.id),
                    group_id=gid,
                    group_key=group_key,
                    range_key=rk,
                    pricing_mode=str(row.pricing_mode),
                    flat_amount=row.flat_amount,
                    base_amount=row.base_amount,
                    rate_per_kg=row.rate_per_kg,
                    base_kg=row.base_kg,
                    active=bool(row.active),
                )
            )

    uniq_pairs = sorted(
        set(range_pairs),
        key=lambda x: (x[0], Decimal("999999999") if x[1] is None else x[1]),
    )
    weight_ranges = [
        MatrixWeightRangeOut(
            range_key=_range_key(min_kg, max_kg),
            min_kg=min_kg,
            max_kg=max_kg,
            sort_order=idx,
            label=_range_label(min_kg, max_kg),
        )
        for idx, (min_kg, max_kg) in enumerate(uniq_pairs)
    ]

    surcharges_raw = (
        db.query(ShippingProviderSurcharge)
        .filter(ShippingProviderSurcharge.scheme_id == scheme_id)
        .order_by(ShippingProviderSurcharge.id.asc())
        .all()
    )
    surcharges: List[SurchargeOut] = [to_surcharge_out(x) for x in surcharges_raw]

    scheme_out = MatrixViewSchemeOut(
        id=int(sch.id),
        warehouse_id=int(sch.warehouse_id),
        shipping_provider_id=int(sch.shipping_provider_id),
        shipping_provider_name=_must_provider_name(sch),
        name=str(sch.name),
        active=bool(sch.active),
        archived_at=sch.archived_at,
        currency=str(sch.currency),
        effective_from=sch.effective_from,
        effective_to=sch.effective_to,
        default_pricing_mode=str(sch.default_pricing_mode),
        billable_weight_rule=sch.billable_weight_rule,
    )

    return MatrixViewOut(
        ok=True,
        data=MatrixViewDataOut(
            scheme=scheme_out,
            groups=group_out,
            weight_ranges=weight_ranges,
            cells=cell_out,
            surcharges=surcharges,
        ),
    )


def _normalized_province_key(province_code: Optional[str], province_name: Optional[str]) -> Tuple[str, str]:
    return (str(province_code or ""), str(province_name or ""))


def _validate_no_overlap(ranges: Iterable[Tuple[Decimal, Optional[Decimal], str]]) -> None:
    ordered = sorted(
        list(ranges),
        key=lambda x: (x[0], Decimal("999999999") if x[1] is None else x[1]),
    )
    prev_min: Optional[Decimal] = None
    prev_max: Optional[Decimal] = None
    prev_key: Optional[str] = None

    for min_kg, max_kg, key in ordered:
        if prev_min is not None:
            prev_end = prev_max
            if prev_end is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"weight_ranges overlap: previous open-ended range conflicts with {key}",
                )
            if min_kg < prev_end:
                raise HTTPException(
                    status_code=422,
                    detail=f"weight_ranges overlap: {prev_key} conflicts with {key}",
                )
        prev_min = min_kg
        prev_max = max_kg
        prev_key = key


def _validate_matrix_patch(payload: PricingMatrixPatchIn) -> None:
    group_keys = set()
    province_owner: Dict[str, str] = {}

    for idx, g in enumerate(payload.groups, start=1):
        if g.group_key in group_keys:
            raise HTTPException(status_code=422, detail=f"duplicate group_key: {g.group_key}")
        group_keys.add(g.group_key)

        if not g.provinces:
            raise HTTPException(
                status_code=422,
                detail=f"group #{idx} must contain at least one province",
            )

        province_seen = set()
        for p in g.provinces:
            province_key = (p.province_name or p.province_code or "").strip()
            if not province_key:
                raise HTTPException(
                    status_code=422,
                    detail=f"group #{idx} province requires province_name or province_code",
                )

            k = _normalized_province_key(p.province_code, p.province_name)
            if k in province_seen:
                raise HTTPException(
                    status_code=422,
                    detail=f"duplicate province in group #{idx}",
                )
            province_seen.add(k)

            label = f"#{idx}"
            owner = province_owner.get(province_key)
            if owner is not None and owner != label:
                raise HTTPException(
                    status_code=422,
                    detail=f"province {province_key} cannot appear in both group {owner} and group {label}",
                )
            province_owner[province_key] = label

    range_keys = set()
    pair_seen = set()
    range_triplets: List[Tuple[Decimal, Optional[Decimal], str]] = []

    for r in payload.weight_ranges:
        if r.range_key in range_keys:
            raise HTTPException(status_code=422, detail=f"duplicate range_key: {r.range_key}")
        range_keys.add(r.range_key)

        pair = (r.min_kg, r.max_kg)
        if pair in pair_seen:
            raise HTTPException(status_code=422, detail=f"duplicate weight range: {r.range_key}")
        pair_seen.add(pair)
        range_triplets.append((r.min_kg, r.max_kg, r.range_key))

    _validate_no_overlap(range_triplets)

    cell_seen = set()
    for c in payload.cells:
        if c.group_key not in group_keys:
            raise HTTPException(status_code=422, detail=f"cell references unknown group_key: {c.group_key}")
        if c.range_key not in range_keys:
            raise HTTPException(status_code=422, detail=f"cell references unknown range_key: {c.range_key}")
        ck = (c.group_key, c.range_key)
        if ck in cell_seen:
            raise HTTPException(
                status_code=422,
                detail=f"duplicate cell: group_key={c.group_key}, range_key={c.range_key}",
            )
        cell_seen.add(ck)

    expected = len(group_keys) * len(range_keys)
    if expected != len(payload.cells):
        raise HTTPException(
            status_code=422,
            detail=(
                f"cells must fully cover group × weight_range matrix; "
                f"expected {expected}, got {len(payload.cells)}"
            ),
        )


def register_pricing_matrix_matrix_editor_routes(router: APIRouter) -> None:
    @router.get(
        "/pricing-schemes/{scheme_id}/matrix-view",
        response_model=MatrixViewOut,
    )
    def get_matrix_view(
        scheme_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")
        return _build_matrix_view(db, scheme_id)

    @router.patch(
        "/pricing-schemes/{scheme_id}/matrix",
        response_model=MatrixViewOut,
    )
    def patch_matrix(
        scheme_id: int = Path(..., ge=1),
        payload: PricingMatrixPatchIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = _load_scheme_or_404(db, scheme_id)
        if sch.archived_at is not None:
            raise HTTPException(status_code=400, detail="Archived scheme cannot be modified")

        _validate_matrix_patch(payload)

        range_map = {
            r.range_key: (r.min_kg, r.max_kg)
            for r in payload.weight_ranges
        }

        existing_groups = (
            db.query(ShippingProviderDestinationGroup)
            .filter(ShippingProviderDestinationGroup.scheme_id == scheme_id)
            .all()
        )
        for g in existing_groups:
            db.delete(g)
        db.flush()

        group_id_by_key: Dict[str, int] = {}

        for idx, g in enumerate(payload.groups, start=1):
            grp = ShippingProviderDestinationGroup(
                scheme_id=int(scheme_id),
                name=f"#{idx}",
                active=bool(g.active),
            )
            db.add(grp)
            db.flush()
            group_id_by_key[g.group_key] = int(grp.id)

            for p in g.provinces:
                db.add(
                    ShippingProviderDestinationGroupMember(
                        group_id=int(grp.id),
                        province_code=p.province_code,
                        province_name=p.province_name,
                    )
                )

        db.flush()

        for c in payload.cells:
            min_kg, max_kg = range_map[c.range_key]
            db.add(
                ShippingProviderPricingMatrix(
                    group_id=group_id_by_key[c.group_key],
                    min_kg=min_kg,
                    max_kg=max_kg,
                    pricing_mode=str(c.pricing_mode),
                    flat_amount=c.flat_amount,
                    base_amount=c.base_amount,
                    rate_per_kg=c.rate_per_kg,
                    base_kg=c.base_kg,
                    active=bool(c.active),
                )
            )

        db.commit()
        return _build_matrix_view(db, scheme_id)
