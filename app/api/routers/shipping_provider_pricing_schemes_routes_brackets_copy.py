# app/api/routers/shipping_provider_pricing_schemes_routes_brackets_copy.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes.schemas import ZoneBracketOut
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.api.routers.shipping_provider_pricing_schemes_routes_brackets_shared import (
    as_bracket_out,
    normalize_mode,
    validate_payload_for_mode,
    handle_integrity_error,
    normalize_conflict_policy,
    normalize_active_policy,
    range_key,
)
from app.db.deps import get_db
from app.models.shipping_provider_zone import ShippingProviderZone
from app.models.shipping_provider_zone_bracket import ShippingProviderZoneBracket


class CopyZoneBracketsIn(BaseModel):
    source_zone_id: int = Field(..., ge=1)

    conflict_policy: str = Field(default="skip")  # skip/overwrite/abort
    active_policy: str = Field(default="preserve")  # preserve/force_active/force_inactive

    pricing_modes: List[str] = Field(default_factory=lambda: ["flat", "linear_total", "step_over"])
    include_inactive: bool = False


class CopyZoneBracketsSummary(BaseModel):
    source_count: int
    created_count: int
    updated_count: int
    skipped_count: int
    failed_count: int


class CopyZoneBracketsOut(BaseModel):
    ok: bool = True
    target_zone_id: int
    source_zone_id: int
    conflict_policy: str
    active_policy: str
    summary: CopyZoneBracketsSummary
    created: List[ZoneBracketOut] = Field(default_factory=list)
    updated: List[ZoneBracketOut] = Field(default_factory=list)
    skipped: List[ZoneBracketOut] = Field(default_factory=list)
    failed: List[Dict[str, Any]] = Field(default_factory=list)


def register_brackets_copy_routes(router: APIRouter) -> None:
    @router.post(
        "/zones/{target_zone_id}/brackets:copy",
        response_model=CopyZoneBracketsOut,
        status_code=status.HTTP_200_OK,
    )
    def copy_zone_brackets(
        target_zone_id: int = Path(..., ge=1),
        payload: CopyZoneBracketsIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        if payload.source_zone_id == target_zone_id:
            raise HTTPException(
                status_code=422, detail="source_zone_id must be different from target_zone_id"
            )

        src_zone = db.get(ShippingProviderZone, payload.source_zone_id)
        if not src_zone:
            raise HTTPException(status_code=404, detail="Source zone not found")

        tgt_zone = db.get(ShippingProviderZone, target_zone_id)
        if not tgt_zone:
            raise HTTPException(status_code=404, detail="Target zone not found")

        if int(src_zone.scheme_id) != int(tgt_zone.scheme_id):
            raise HTTPException(
                status_code=409, detail="Source/Target zones must belong to the same scheme"
            )

        conflict_policy = normalize_conflict_policy(payload.conflict_policy)
        active_policy = normalize_active_policy(payload.active_policy)
        modes = [normalize_mode(m) for m in (payload.pricing_modes or [])]

        q_src = db.query(ShippingProviderZoneBracket).filter(
            ShippingProviderZoneBracket.zone_id == src_zone.id
        )
        if not payload.include_inactive:
            q_src = q_src.filter(ShippingProviderZoneBracket.active.is_(True))
        if modes:
            q_src = q_src.filter(ShippingProviderZoneBracket.pricing_mode.in_(modes))
        src_brackets = q_src.order_by(
            ShippingProviderZoneBracket.min_kg.asc(),
            ShippingProviderZoneBracket.max_kg.asc().nulls_last(),
            ShippingProviderZoneBracket.id.asc(),
        ).all()

        tgt_brackets = (
            db.query(ShippingProviderZoneBracket)
            .filter(ShippingProviderZoneBracket.zone_id == target_zone_id)
            .order_by(
                ShippingProviderZoneBracket.min_kg.asc(),
                ShippingProviderZoneBracket.max_kg.asc().nulls_last(),
                ShippingProviderZoneBracket.id.asc(),
            )
            .all()
        )
        tgt_index: Dict[Tuple[Decimal, Optional[Decimal]], ShippingProviderZoneBracket] = {
            range_key(b.min_kg, b.max_kg): b for b in tgt_brackets
        }

        created: List[ZoneBracketOut] = []
        updated: List[ZoneBracketOut] = []
        skipped: List[ZoneBracketOut] = []
        failed: List[Dict[str, Any]] = []

        def resolve_active(src_active: bool) -> bool:
            if active_policy == "preserve":
                return bool(src_active)
            if active_policy == "force_active":
                return True
            if active_policy == "force_inactive":
                return False
            return bool(src_active)

        try:
            for sb in src_brackets:
                key = range_key(sb.min_kg, sb.max_kg)
                tb = tgt_index.get(key)

                new_mode = normalize_mode(sb.pricing_mode)
                new_flat = sb.flat_amount
                new_base = sb.base_amount
                new_rate = sb.rate_per_kg
                new_base_kg = getattr(sb, "base_kg", None)
                new_active = resolve_active(bool(sb.active))

                validate_payload_for_mode(new_mode, new_flat, new_base, new_rate, new_base_kg)

                if tb is None:
                    nb = ShippingProviderZoneBracket(
                        zone_id=target_zone_id,
                        min_kg=sb.min_kg,
                        max_kg=sb.max_kg,
                        pricing_mode=new_mode,
                        flat_amount=new_flat,
                        base_amount=new_base,
                        rate_per_kg=new_rate,
                        base_kg=new_base_kg,
                        active=new_active,
                    )
                    db.add(nb)
                    try:
                        db.flush()
                    except IntegrityError as e:
                        db.rollback()
                        if conflict_policy == "abort":
                            handle_integrity_error(e)
                        failed.append(
                            {
                                "min_kg": float(sb.min_kg),
                                "max_kg": None if sb.max_kg is None else float(sb.max_kg),
                                "error": "integrity_error",
                                "detail": str(getattr(e, "orig", e)),
                            }
                        )
                        continue

                    db.refresh(nb)
                    tgt_index[key] = nb
                    created.append(as_bracket_out(nb))
                    continue

                if conflict_policy == "skip":
                    skipped.append(as_bracket_out(tb))
                    continue

                if conflict_policy == "abort":
                    raise HTTPException(
                        status_code=409,
                        detail=f"Bracket range conflict at min_kg={float(sb.min_kg)} max_kg={None if sb.max_kg is None else float(sb.max_kg)}",
                    )

                tb.pricing_mode = new_mode
                tb.flat_amount = new_flat
                tb.base_amount = new_base
                tb.rate_per_kg = new_rate
                tb.base_kg = new_base_kg
                tb.active = new_active

                try:
                    db.flush()
                except IntegrityError as e:
                    db.rollback()
                    failed.append(
                        {
                            "id": tb.id,
                            "min_kg": float(tb.min_kg),
                            "max_kg": None if tb.max_kg is None else float(tb.max_kg),
                            "error": "integrity_error",
                            "detail": str(getattr(e, "orig", e)),
                        }
                    )
                    continue

                updated.append(as_bracket_out(tb))

            db.commit()
        except HTTPException:
            db.rollback()
            raise
        except IntegrityError as e:
            db.rollback()
            handle_integrity_error(e)

        summary = CopyZoneBracketsSummary(
            source_count=len(src_brackets),
            created_count=len(created),
            updated_count=len(updated),
            skipped_count=len(skipped),
            failed_count=len(failed),
        )

        return CopyZoneBracketsOut(
            ok=True,
            target_zone_id=target_zone_id,
            source_zone_id=payload.source_zone_id,
            conflict_policy=conflict_policy,
            active_policy=active_policy,
            summary=summary,
            created=created,
            updated=updated,
            skipped=skipped,
            failed=failed,
        )
