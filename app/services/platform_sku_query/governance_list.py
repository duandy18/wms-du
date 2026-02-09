# app/services/platform_sku_query/governance_list.py
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.api.schemas.psku_governance import (
    PskuBindCtx,
    PskuGovernanceActionHint,
    PskuGovernanceOut,
    PskuGovernanceItem,
    PskuGovernanceStatus,
)
from app.models.fsku import Fsku, FskuComponent
from app.models.platform_sku_binding import PlatformSkuBinding
from app.models.platform_sku_mirror import PlatformSkuMirror
from app.models.store import Store
from app.services.platform_sku_query._common import (
    build_bindings_only_base,
    build_mirror_base,
    fetch_mirror_first_page,
    load_current_bindings_map,
    uniq_ints,
)


def list_governance(
    db: Session,
    *,
    platform: str | None,
    store_id: int | None,
    status: str | None,
    action: str | None,
    limit: int,
    offset: int,
    q: str | None,
) -> PskuGovernanceOut:
    plat = (platform or "").strip().upper() or None
    st = (status or "").strip().upper() or None
    act = (action or "").strip().upper() or None

    # action -> status（后端裁决，避免前端推断）
    action_to_status = {
        "OK": "BOUND",
        "BIND_FIRST": "UNBOUND",
        "MIGRATE_LEGACY": "LEGACY_ITEM_BOUND",
    }
    if act in action_to_status:
        required = action_to_status[act]
        if st and st != required:
            return PskuGovernanceOut(items=[], total=0, limit=limit, offset=offset)
        st = required

    q2 = (q or "").strip()
    like = f"%{q2}%" if q2 else None

    mirror_base = build_mirror_base(store_id=store_id, platform_upper=plat, q=None)
    bindings_only_base = build_bindings_only_base(store_id=store_id, platform_upper=plat, q=None)

    # q：mirror字段 OR (exists current binding -> fsku(code/name))
    if like:
        Bm = aliased(PlatformSkuBinding)
        mirror_fsku_hit = (
            select(1)
            .select_from(Bm)
            .join(Fsku, Fsku.id == Bm.fsku_id)
            .where(
                Bm.effective_to.is_(None),
                Bm.platform == PlatformSkuMirror.platform,
                Bm.store_id == PlatformSkuMirror.store_id,
                Bm.platform_sku_id == PlatformSkuMirror.platform_sku_id,
                Bm.fsku_id.is_not(None),
                (Fsku.code.ilike(like) | Fsku.name.ilike(like)),
            )
            .limit(1)
        )

        mirror_base = mirror_base.where(
            PlatformSkuMirror.platform_sku_id.ilike(like)
            | PlatformSkuMirror.sku_name.ilike(like)
            | PlatformSkuMirror.spec.ilike(like)
            | mirror_fsku_hit.exists()
        )

        Bb = aliased(PlatformSkuBinding)
        bindings_fsku_hit = (
            select(1)
            .select_from(Bb)
            .join(Fsku, Fsku.id == Bb.fsku_id)
            .where(
                Bb.effective_to.is_(None),
                Bb.platform == PlatformSkuBinding.platform,
                Bb.store_id == PlatformSkuBinding.store_id,
                Bb.platform_sku_id == PlatformSkuBinding.platform_sku_id,
                Bb.fsku_id.is_not(None),
                (Fsku.code.ilike(like) | Fsku.name.ilike(like)),
            )
            .limit(1)
        )

        bindings_only_base = bindings_only_base.where(PlatformSkuBinding.platform_sku_id.ilike(like) | bindings_fsku_hit.exists())

    # status 过滤（DB 侧）
    if st in ("BOUND", "LEGACY_ITEM_BOUND", "UNBOUND"):
        if st == "BOUND":
            cur = (
                select(1)
                .select_from(PlatformSkuBinding)
                .where(
                    PlatformSkuBinding.effective_to.is_(None),
                    PlatformSkuBinding.platform == PlatformSkuMirror.platform,
                    PlatformSkuBinding.store_id == PlatformSkuMirror.store_id,
                    PlatformSkuBinding.platform_sku_id == PlatformSkuMirror.platform_sku_id,
                    PlatformSkuBinding.fsku_id.is_not(None),
                )
                .limit(1)
            )
            mirror_base = mirror_base.where(cur.exists())

            bindings_only_base = (
                select(PlatformSkuBinding.platform, PlatformSkuBinding.store_id, PlatformSkuBinding.platform_sku_id)
                .where(PlatformSkuBinding.effective_to.is_(None), PlatformSkuBinding.fsku_id.is_not(None))
                .distinct()
            )
            if plat:
                from sqlalchemy import func

                bindings_only_base = bindings_only_base.where(func.upper(PlatformSkuBinding.platform) == plat)
            if store_id is not None:
                bindings_only_base = bindings_only_base.where(PlatformSkuBinding.store_id == int(store_id))

            if like:
                Bb2 = aliased(PlatformSkuBinding)
                fsku_hit2 = (
                    select(1)
                    .select_from(Bb2)
                    .join(Fsku, Fsku.id == Bb2.fsku_id)
                    .where(
                        Bb2.effective_to.is_(None),
                        Bb2.platform == PlatformSkuBinding.platform,
                        Bb2.store_id == PlatformSkuBinding.store_id,
                        Bb2.platform_sku_id == PlatformSkuBinding.platform_sku_id,
                        Bb2.fsku_id.is_not(None),
                        (Fsku.code.ilike(like) | Fsku.name.ilike(like)),
                    )
                    .limit(1)
                )
                bindings_only_base = bindings_only_base.where(PlatformSkuBinding.platform_sku_id.ilike(like) | fsku_hit2.exists())

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
            bindings_only_base = bindings_only_base.where(~mirror_exists.exists())

        elif st == "LEGACY_ITEM_BOUND":
            cur = (
                select(1)
                .select_from(PlatformSkuBinding)
                .where(
                    PlatformSkuBinding.effective_to.is_(None),
                    PlatformSkuBinding.platform == PlatformSkuMirror.platform,
                    PlatformSkuBinding.store_id == PlatformSkuMirror.store_id,
                    PlatformSkuBinding.platform_sku_id == PlatformSkuMirror.platform_sku_id,
                    PlatformSkuBinding.fsku_id.is_(None),
                    PlatformSkuBinding.item_id.is_not(None),
                )
                .limit(1)
            )
            mirror_base = mirror_base.where(cur.exists())

            bindings_only_base = (
                select(PlatformSkuBinding.platform, PlatformSkuBinding.store_id, PlatformSkuBinding.platform_sku_id)
                .where(
                    PlatformSkuBinding.effective_to.is_(None),
                    PlatformSkuBinding.fsku_id.is_(None),
                    PlatformSkuBinding.item_id.is_not(None),
                )
                .distinct()
            )
            if plat:
                from sqlalchemy import func

                bindings_only_base = bindings_only_base.where(func.upper(PlatformSkuBinding.platform) == plat)
            if store_id is not None:
                bindings_only_base = bindings_only_base.where(PlatformSkuBinding.store_id == int(store_id))
            if like:
                bindings_only_base = bindings_only_base.where(PlatformSkuBinding.platform_sku_id.ilike(like))

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
            bindings_only_base = bindings_only_base.where(~mirror_exists.exists())

        else:  # UNBOUND
            cur_target = (
                select(1)
                .select_from(PlatformSkuBinding)
                .where(
                    PlatformSkuBinding.effective_to.is_(None),
                    PlatformSkuBinding.platform == PlatformSkuMirror.platform,
                    PlatformSkuBinding.store_id == PlatformSkuMirror.store_id,
                    PlatformSkuBinding.platform_sku_id == PlatformSkuMirror.platform_sku_id,
                    (PlatformSkuBinding.fsku_id.is_not(None) | PlatformSkuBinding.item_id.is_not(None)),
                )
                .limit(1)
            )
            mirror_base = mirror_base.where(~cur_target.exists())

            B2 = aliased(PlatformSkuBinding)
            cur_target2 = (
                select(1)
                .select_from(B2)
                .where(
                    B2.effective_to.is_(None),
                    B2.platform == PlatformSkuBinding.platform,
                    B2.store_id == PlatformSkuBinding.store_id,
                    B2.platform_sku_id == PlatformSkuBinding.platform_sku_id,
                    (B2.fsku_id.is_not(None) | B2.item_id.is_not(None)),
                )
                .limit(1)
            )
            bindings_only_base = bindings_only_base.where(~cur_target2.exists())
            if like:
                bindings_only_base = bindings_only_base.where(PlatformSkuBinding.platform_sku_id.ilike(like))

    page = fetch_mirror_first_page(
        db,
        mirror_base=mirror_base,
        bindings_only_base=bindings_only_base,
        limit=limit,
        offset=offset,
        mirror_order_by=(PlatformSkuMirror.store_id, PlatformSkuMirror.platform_sku_id),
        bindings_only_order_by=(PlatformSkuBinding.store_id, PlatformSkuBinding.platform_sku_id),
    )

    bindings = load_current_bindings_map(db, store_id=store_id, platform_upper=plat)

    store_ids: set[int] = set()
    fsku_ids: set[int] = set()

    for m in page.mirror_rows:
        sid = int(m.store_id)
        store_ids.add(sid)
        b = bindings.get((m.platform, sid, m.platform_sku_id))
        if b and b.fsku_id:
            fsku_ids.add(int(b.fsku_id))

    for p2, sid2, psku2 in page.bindings_only_rows:
        store_ids.add(int(sid2))
        b = bindings.get((p2, int(sid2), psku2))
        if b and b.fsku_id:
            fsku_ids.add(int(b.fsku_id))

    store_name_map: dict[int, str] = {}
    if store_ids:
        for s in db.scalars(select(Store).where(Store.id.in_(sorted(store_ids)))).all():
            store_name_map[int(s.id)] = str(s.name)

    fsku_map: dict[int, Fsku] = {}
    if fsku_ids:
        for f in db.scalars(select(Fsku).where(Fsku.id.in_(sorted(fsku_ids)))).all():
            fsku_map[int(f.id)] = f

    comp_item_ids: dict[int, list[int]] = {}
    if fsku_ids:
        rows = db.execute(
            select(FskuComponent.fsku_id, FskuComponent.item_id).where(FskuComponent.fsku_id.in_(sorted(fsku_ids)))
        ).all()
        for fid, iid in rows:
            comp_item_ids.setdefault(int(fid), []).append(int(iid))

    def _gov(b: PlatformSkuBinding | None) -> PskuGovernanceStatus:
        if b is None:
            return PskuGovernanceStatus(status="UNBOUND")
        if b.fsku_id is None and b.item_id is not None:
            return PskuGovernanceStatus(status="LEGACY_ITEM_BOUND")
        if b.fsku_id is None:
            return PskuGovernanceStatus(status="UNBOUND")
        return PskuGovernanceStatus(status="BOUND")

    def _action(b: PlatformSkuBinding | None) -> PskuGovernanceActionHint:
        if b is None:
            return PskuGovernanceActionHint(action="BIND_FIRST", required=["fsku_id"])
        if b.fsku_id is None and b.item_id is not None:
            return PskuGovernanceActionHint(action="MIGRATE_LEGACY", required=["binding_id", "to_fsku_id"])
        if b.fsku_id is None:
            return PskuGovernanceActionHint(action="BIND_FIRST", required=["fsku_id"])
        return PskuGovernanceActionHint(action="OK", required=[])

    def _bind_ctx_for(item_platform_sku_id: str, sku_name: str | None, spec: str | None) -> PskuBindCtx:
        base = (sku_name or "").strip() or item_platform_sku_id
        s = (spec or "").strip()
        suggest_q = f"{base} {s}".strip()
        suggest_fsku_query = base
        return PskuBindCtx(suggest_q=suggest_q, suggest_fsku_query=suggest_fsku_query)

    def _fresh(has_mirror: bool) -> str:
        return "ok" if has_mirror else "missing"

    items: list[PskuGovernanceItem] = []

    for m in page.mirror_rows:
        sid = int(m.store_id)
        b = bindings.get((m.platform, sid, m.platform_sku_id))

        fsku = fsku_map.get(int(b.fsku_id)) if (b and b.fsku_id) else None
        cids = comp_item_ids.get(int(fsku.id)) if fsku else None

        ah = _action(b)
        bind_ctx = _bind_ctx_for(m.platform_sku_id, m.sku_name, m.spec) if ah.action == "BIND_FIRST" else None

        items.append(
            PskuGovernanceItem(
                platform=str(m.platform or "").strip().upper(),
                store_id=sid,
                store_name=store_name_map.get(sid),
                platform_sku_id=m.platform_sku_id,
                sku_name=m.sku_name,
                spec=m.spec,
                mirror_freshness=_fresh(True),
                binding_id=int(b.id) if b is not None else None,
                fsku_id=int(fsku.id) if fsku else None,
                fsku_code=fsku.code if fsku else None,
                fsku_name=fsku.name if fsku else None,
                fsku_status=fsku.status if fsku else None,
                governance=_gov(b),
                action_hint=ah,
                bind_ctx=bind_ctx,
                component_item_ids=uniq_ints(cids or []),
            )
        )

    for p2, sid2, psku2 in page.bindings_only_rows:
        k2 = (p2, int(sid2), psku2)
        if k2 in page.mirror_keys_in_page:
            continue

        b = bindings.get(k2)
        fsku = fsku_map.get(int(b.fsku_id)) if (b and b.fsku_id) else None
        cids = comp_item_ids.get(int(fsku.id)) if fsku else None

        ah = _action(b)
        bind_ctx = _bind_ctx_for(psku2, None, None) if ah.action == "BIND_FIRST" else None

        items.append(
            PskuGovernanceItem(
                platform=str(p2 or "").strip().upper(),
                store_id=int(sid2),
                store_name=store_name_map.get(int(sid2)),
                platform_sku_id=psku2,
                sku_name=None,
                spec=None,
                mirror_freshness=_fresh(False),
                binding_id=int(b.id) if b is not None else None,
                fsku_id=int(fsku.id) if fsku else None,
                fsku_code=fsku.code if fsku else None,
                fsku_name=fsku.name if fsku else None,
                fsku_status=fsku.status if fsku else None,
                governance=_gov(b),
                action_hint=ah,
                bind_ctx=bind_ctx,
                component_item_ids=uniq_ints(cids or []),
            )
        )

    total = page.mirror_total + page.bindings_only_total
    return PskuGovernanceOut(items=items, total=total, limit=limit, offset=offset)
