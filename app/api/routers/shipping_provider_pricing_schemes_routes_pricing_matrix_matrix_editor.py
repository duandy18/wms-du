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
    MatrixModuleOut,
    MatrixModuleRangeOut,
    MatrixViewDataOut,
    MatrixViewOut,
    MatrixViewSchemeOut,
    PricingMatrixPutIn,
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
from app.models.shipping_provider_pricing_scheme_module import ShippingProviderPricingSchemeModule
from app.models.shipping_provider_pricing_scheme_module_range import (
    ShippingProviderPricingSchemeModuleRange,
)
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


def _load_modules_ranges_groups_members_rows(
    db: Session,
    scheme_id: int,
) -> Tuple[
    List[ShippingProviderPricingSchemeModule],
    Dict[int, List[ShippingProviderPricingSchemeModuleRange]],
    List[ShippingProviderDestinationGroup],
    Dict[int, List[ShippingProviderDestinationGroupMember]],
    Dict[int, List[ShippingProviderPricingMatrix]],
]:
    modules = (
        db.query(ShippingProviderPricingSchemeModule)
        .filter(ShippingProviderPricingSchemeModule.scheme_id == scheme_id)
        .order_by(
            ShippingProviderPricingSchemeModule.sort_order.asc(),
            ShippingProviderPricingSchemeModule.id.asc(),
        )
        .all()
    )
    module_ids = [int(m.id) for m in modules]

    ranges_by_module: Dict[int, List[ShippingProviderPricingSchemeModuleRange]] = {}
    groups: List[ShippingProviderDestinationGroup] = []
    members_by_group: Dict[int, List[ShippingProviderDestinationGroupMember]] = {}
    rows_by_group: Dict[int, List[ShippingProviderPricingMatrix]] = {}

    if module_ids:
        ranges = (
            db.query(ShippingProviderPricingSchemeModuleRange)
            .filter(ShippingProviderPricingSchemeModuleRange.module_id.in_(module_ids))
            .order_by(
                ShippingProviderPricingSchemeModuleRange.module_id.asc(),
                ShippingProviderPricingSchemeModuleRange.sort_order.asc(),
                ShippingProviderPricingSchemeModuleRange.id.asc(),
            )
            .all()
        )
        for r in ranges:
            ranges_by_module.setdefault(int(r.module_id), []).append(r)

        groups = (
            db.query(ShippingProviderDestinationGroup)
            .filter(ShippingProviderDestinationGroup.scheme_id == scheme_id)
            .order_by(
                ShippingProviderDestinationGroup.module_id.asc(),
                ShippingProviderDestinationGroup.sort_order.asc(),
                ShippingProviderDestinationGroup.id.asc(),
            )
            .all()
        )
        group_ids = [int(g.id) for g in groups]

        if group_ids:
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
                    ShippingProviderPricingMatrix.module_range_id.asc(),
                    ShippingProviderPricingMatrix.id.asc(),
                )
                .all()
            )
            for row in rows:
                rows_by_group.setdefault(int(row.group_id), []).append(row)

    return modules, ranges_by_module, groups, members_by_group, rows_by_group


def _build_matrix_view(db: Session, scheme_id: int) -> MatrixViewOut:
    sch = _load_scheme_or_404(db, scheme_id)
    modules, ranges_by_module, groups, members_by_group, rows_by_group = _load_modules_ranges_groups_members_rows(db, scheme_id)

    module_out: List[MatrixModuleOut] = []
    group_out: List[MatrixGroupOut] = []
    cell_out: List[MatrixCellOut] = []

    module_key_by_id: Dict[int, str] = {}
    range_key_by_id: Dict[int, str] = {}

    for mod in modules:
        mid = int(mod.id)
        module_key = f"m:{mid}"
        module_key_by_id[mid] = module_key

        ranges_out: List[MatrixModuleRangeOut] = []
        for r in ranges_by_module.get(mid, []):
            rid = int(r.id)
            range_key = f"r:{rid}"
            range_key_by_id[rid] = range_key
            ranges_out.append(
                MatrixModuleRangeOut(
                    id=rid,
                    module_id=mid,
                    module_key=module_key,
                    range_key=range_key,
                    min_kg=r.min_kg,
                    max_kg=r.max_kg,
                    sort_order=int(r.sort_order),
                    label=_range_label(r.min_kg, r.max_kg),
                )
            )

        module_out.append(
            MatrixModuleOut(
                id=mid,
                module_key=module_key,
                scheme_id=int(mod.scheme_id),
                module_code=str(mod.module_code),
                name=str(mod.name),
                sort_order=int(mod.sort_order),
                ranges=ranges_out,
            )
        )

    for g in groups:
        gid = int(g.id)
        mid = int(g.module_id)
        module_key = module_key_by_id[mid]
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
                module_id=mid,
                module_key=module_key,
                name=str(g.name),
                sort_order=int(g.sort_order),
                active=bool(g.active),
                provinces=provinces,
            )
        )

        for row in rows_by_group.get(gid, []):
            module_range_id = int(row.module_range_id)
            range_key = range_key_by_id.get(module_range_id)
            if not range_key:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"Pricing matrix references missing module range "
                        f"(row_id={row.id}, module_range_id={module_range_id})"
                    ),
                )

            cell_out.append(
                MatrixCellOut(
                    cell_key=f"{group_key}|{range_key}",
                    pricing_matrix_id=int(row.id),
                    module_id=mid,
                    module_key=module_key,
                    group_id=gid,
                    group_key=group_key,
                    range_key=range_key,
                    pricing_mode=str(row.pricing_mode),
                    flat_amount=row.flat_amount,
                    base_amount=row.base_amount,
                    rate_per_kg=row.rate_per_kg,
                    base_kg=row.base_kg,
                    active=bool(row.active),
                )
            )

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
        status=str(sch.status),
        archived_at=sch.archived_at,
        currency=str(sch.currency),
        effective_from=sch.effective_from,
        effective_to=sch.effective_to,
        default_pricing_mode=str(sch.default_pricing_mode),
        billable_weight_strategy=str(sch.billable_weight_strategy),
        volume_divisor=None if sch.volume_divisor is None else int(sch.volume_divisor),
        rounding_mode=str(sch.rounding_mode),
        rounding_step_kg=None if sch.rounding_step_kg is None else float(sch.rounding_step_kg),
        min_billable_weight_kg=None if sch.min_billable_weight_kg is None else float(sch.min_billable_weight_kg),
    )

    return MatrixViewOut(
        ok=True,
        data=MatrixViewDataOut(
            scheme=scheme_out,
            modules=module_out,
            groups=group_out,
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
    prev_max: Optional[Decimal] = None
    prev_key: Optional[str] = None

    for min_kg, max_kg, key in ordered:
        if prev_key is not None:
            if prev_max is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"weight_ranges overlap: previous open-ended range conflicts with {key}",
                )
            if min_kg < prev_max:
                raise HTTPException(
                    status_code=422,
                    detail=f"weight_ranges overlap: {prev_key} conflicts with {key}",
                )
        prev_max = max_kg
        prev_key = key


def _validate_matrix_put(payload: PricingMatrixPutIn) -> None:
    if not payload.modules:
        raise HTTPException(status_code=422, detail="modules must not be empty")

    module_keys = set()
    module_codes = set()
    module_label_by_key: Dict[str, str] = {}

    for idx, m in enumerate(payload.modules, start=1):
        if m.module_key in module_keys:
            raise HTTPException(status_code=422, detail=f"duplicate module_key: {m.module_key}")
        if m.module_code in module_codes:
            raise HTTPException(status_code=422, detail=f"duplicate module_code: {m.module_code}")
        module_keys.add(m.module_key)
        module_codes.add(m.module_code)
        module_label_by_key[m.module_key] = m.module_code

    if module_codes != {"standard", "other"}:
        raise HTTPException(status_code=422, detail="modules must contain exactly: standard, other")

    group_keys = set()
    province_owner: Dict[Tuple[str, str], str] = {}
    groups_by_module: Dict[str, List[str]] = {k: [] for k in module_keys}

    for idx, g in enumerate(payload.groups, start=1):
        if g.group_key in group_keys:
            raise HTTPException(status_code=422, detail=f"duplicate group_key: {g.group_key}")
        if g.module_key not in module_keys:
            raise HTTPException(status_code=422, detail=f"group references unknown module_key: {g.module_key}")
        if not g.provinces:
            raise HTTPException(status_code=422, detail=f"group #{idx} must contain at least one province")

        group_keys.add(g.group_key)
        groups_by_module[g.module_key].append(g.group_key)

        province_seen = set()
        for p in g.provinces:
            k = _normalized_province_key(p.province_code, p.province_name)
            if k in province_seen:
                raise HTTPException(status_code=422, detail=f"duplicate province in group #{idx}")
            province_seen.add(k)

            owner = province_owner.get(k)
            if owner is not None and owner != g.group_key:
                label = p.province_name or p.province_code or "unknown"
                raise HTTPException(
                    status_code=422,
                    detail=f"province {label} cannot appear in both group {owner} and group {g.group_key}",
                )
            province_owner[k] = g.group_key

    range_keys = set()
    ranges_by_module: Dict[str, List[Tuple[Decimal, Optional[Decimal], str]]] = {k: [] for k in module_keys}
    range_module_by_key: Dict[str, str] = {}

    for r in payload.weight_ranges:
        if r.range_key in range_keys:
            raise HTTPException(status_code=422, detail=f"duplicate range_key: {r.range_key}")
        if r.module_key not in module_keys:
            raise HTTPException(status_code=422, detail=f"weight_range references unknown module_key: {r.module_key}")
        range_keys.add(r.range_key)
        range_module_by_key[r.range_key] = r.module_key
        ranges_by_module[r.module_key].append((r.min_kg, r.max_kg, r.range_key))

    for module_key, xs in ranges_by_module.items():
        if not xs:
            raise HTTPException(
                status_code=422,
                detail=f"module {module_label_by_key[module_key]} must contain at least one weight range",
            )
        _validate_no_overlap(xs)

    for module_key, xs in groups_by_module.items():
        if not xs:
            raise HTTPException(
                status_code=422,
                detail=f"module {module_label_by_key[module_key]} must contain at least one group",
            )

    cell_seen = set()
    expected = 0
    for module_key in module_keys:
        expected += len(groups_by_module[module_key]) * len(ranges_by_module[module_key])

    group_module_by_key = {g.group_key: g.module_key for g in payload.groups}

    for c in payload.cells:
        if c.group_key not in group_keys:
            raise HTTPException(status_code=422, detail=f"cell references unknown group_key: {c.group_key}")
        if c.range_key not in range_keys:
            raise HTTPException(status_code=422, detail=f"cell references unknown range_key: {c.range_key}")

        g_module = group_module_by_key[c.group_key]
        r_module = range_module_by_key[c.range_key]
        if g_module != r_module:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"cell crosses modules: group_key={c.group_key} "
                    f"module_key={g_module} range_key={c.range_key} module_key={r_module}"
                ),
            )

        ck = (c.group_key, c.range_key)
        if ck in cell_seen:
            raise HTTPException(
                status_code=422,
                detail=f"duplicate cell: group_key={c.group_key}, range_key={c.range_key}",
            )
        cell_seen.add(ck)

    if expected != len(payload.cells):
        raise HTTPException(
            status_code=422,
            detail=f"cells must fully cover group × weight_range matrix; expected {expected}, got {len(payload.cells)}",
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

    @router.put(
        "/pricing-schemes/{scheme_id}/matrix",
        response_model=MatrixViewOut,
    )
    def put_matrix(
        scheme_id: int = Path(..., ge=1),
        payload: PricingMatrixPutIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        sch = _load_scheme_or_404(db, scheme_id)
        if str(sch.status) != "draft":
            raise HTTPException(status_code=400, detail="Only draft scheme can be modified")

        _validate_matrix_put(payload)

        existing_modules = (
            db.query(ShippingProviderPricingSchemeModule)
            .filter(ShippingProviderPricingSchemeModule.scheme_id == scheme_id)
            .all()
        )
        for mod in existing_modules:
            db.delete(mod)
        db.flush()

        module_id_by_key: Dict[str, int] = {}
        module_key_by_id: Dict[int, str] = {}
        module_code_by_key: Dict[str, str] = {}
        range_id_by_key: Dict[str, int] = {}
        range_module_id_by_key: Dict[str, int] = {}
        group_id_by_key: Dict[str, int] = {}

        sorted_modules = sorted(
            enumerate(payload.modules),
            key=lambda x: (x[1].sort_order if x[1].sort_order is not None else x[0]),
        )
        for idx, mod_item in sorted_modules:
            mod = ShippingProviderPricingSchemeModule(
                scheme_id=int(scheme_id),
                module_code=str(mod_item.module_code),
                name=str(mod_item.name),
                sort_order=int(mod_item.sort_order if mod_item.sort_order is not None else idx),
            )
            db.add(mod)
            db.flush()

            mid = int(mod.id)
            module_id_by_key[mod_item.module_key] = mid
            module_key_by_id[mid] = mod_item.module_key
            module_code_by_key[mod_item.module_key] = mod_item.module_code

        ranges_by_module: Dict[str, List[Tuple[int, object]]] = {}
        for idx, r in enumerate(payload.weight_ranges):
            ranges_by_module.setdefault(r.module_key, []).append((idx, r))

        for module_key, xs in ranges_by_module.items():
            xs_sorted = sorted(xs, key=lambda x: (x[1].sort_order if x[1].sort_order is not None else x[0]))
            for idx, r in xs_sorted:
                row = ShippingProviderPricingSchemeModuleRange(
                    module_id=module_id_by_key[module_key],
                    min_kg=r.min_kg,
                    max_kg=r.max_kg,
                    sort_order=int(r.sort_order if r.sort_order is not None else idx),
                )
                db.add(row)
                db.flush()
                rid = int(row.id)
                range_id_by_key[r.range_key] = rid
                range_module_id_by_key[r.range_key] = int(row.module_id)

        groups_by_module: Dict[str, List[Tuple[int, object]]] = {}
        for idx, g in enumerate(payload.groups):
            groups_by_module.setdefault(g.module_key, []).append((idx, g))

        for module_key, xs in groups_by_module.items():
            xs_sorted = sorted(xs, key=lambda x: (x[1].sort_order if x[1].sort_order is not None else x[0]))
            for idx, g in xs_sorted:
                grp = ShippingProviderDestinationGroup(
                    scheme_id=int(scheme_id),
                    module_id=module_id_by_key[module_key],
                    name=str(g.name),
                    sort_order=int(g.sort_order if g.sort_order is not None else idx),
                    active=bool(g.active),
                )
                db.add(grp)
                db.flush()
                gid = int(grp.id)
                group_id_by_key[g.group_key] = gid

                for p in g.provinces:
                    db.add(
                        ShippingProviderDestinationGroupMember(
                            group_id=gid,
                            province_code=p.province_code,
                            province_name=p.province_name,
                        )
                    )

        db.flush()

        for c in payload.cells:
            module_range_id = range_id_by_key[c.range_key]
            range_module_id = range_module_id_by_key[c.range_key]
            db.add(
                ShippingProviderPricingMatrix(
                    group_id=group_id_by_key[c.group_key],
                    module_range_id=module_range_id,
                    range_module_id=range_module_id,
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
