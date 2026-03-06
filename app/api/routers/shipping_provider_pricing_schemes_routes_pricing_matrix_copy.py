# app/api/routers/shipping_provider_pricing_schemes_routes_pricing_matrix_copy.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes.schemas import PricingMatrixOut
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.api.routers.shipping_provider_pricing_schemes_routes_pricing_matrix_shared import (
    as_pricing_matrix_out,
    handle_integrity_error,
    normalize_active_policy,
    normalize_conflict_policy,
    normalize_mode,
    range_key,
    validate_payload_for_mode,
)
from app.db.deps import get_db
from app.models.shipping_provider_destination_group import ShippingProviderDestinationGroup
from app.models.shipping_provider_pricing_matrix import ShippingProviderPricingMatrix


class CopyPricingMatrixIn(BaseModel):
    source_group_id: int = Field(..., ge=1)

    conflict_policy: str = Field(default="skip")  # skip/overwrite/abort
    active_policy: str = Field(default="preserve")  # preserve/force_active/force_inactive

    pricing_modes: List[str] = Field(default_factory=lambda: ["flat", "linear_total", "step_over"])
    include_inactive: bool = False


class CopyPricingMatrixSummary(BaseModel):
    source_count: int
    created_count: int
    updated_count: int
    skipped_count: int
    failed_count: int


class CopyPricingMatrixOut(BaseModel):
    ok: bool = True
    target_group_id: int
    source_group_id: int
    conflict_policy: str
    active_policy: str
    summary: CopyPricingMatrixSummary
    created: List[PricingMatrixOut] = Field(default_factory=list)
    updated: List[PricingMatrixOut] = Field(default_factory=list)
    skipped: List[PricingMatrixOut] = Field(default_factory=list)
    failed: List[Dict[str, Any]] = Field(default_factory=list)


def register_pricing_matrix_copy_routes(router: APIRouter) -> None:
    @router.post(
        "/destination-groups/{target_group_id}/pricing-matrix:copy",
        response_model=CopyPricingMatrixOut,
        status_code=status.HTTP_200_OK,
    )
    def copy_pricing_matrix(
        target_group_id: int = Path(..., ge=1),
        payload: CopyPricingMatrixIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_perm(db, user, "config.store.write")

        if payload.source_group_id == target_group_id:
            raise HTTPException(
                status_code=422,
                detail="source_group_id must be different from target_group_id",
            )

        src_group = db.get(ShippingProviderDestinationGroup, payload.source_group_id)
        if not src_group:
            raise HTTPException(status_code=404, detail="Source destination group not found")

        tgt_group = db.get(ShippingProviderDestinationGroup, target_group_id)
        if not tgt_group:
            raise HTTPException(status_code=404, detail="Target destination group not found")

        if int(src_group.scheme_id) != int(tgt_group.scheme_id):
            raise HTTPException(
                status_code=409,
                detail="Source/Target destination groups must belong to the same scheme",
            )

        conflict_policy = normalize_conflict_policy(payload.conflict_policy)
        active_policy = normalize_active_policy(payload.active_policy)
        modes = [normalize_mode(m) for m in (payload.pricing_modes or [])]

        q_src = db.query(ShippingProviderPricingMatrix).filter(
            ShippingProviderPricingMatrix.group_id == src_group.id
        )
        if not payload.include_inactive:
            q_src = q_src.filter(ShippingProviderPricingMatrix.active.is_(True))
        if modes:
            q_src = q_src.filter(ShippingProviderPricingMatrix.pricing_mode.in_(modes))

        src_rows = q_src.order_by(
            ShippingProviderPricingMatrix.min_kg.asc(),
            ShippingProviderPricingMatrix.max_kg.asc().nulls_last(),
            ShippingProviderPricingMatrix.id.asc(),
        ).all()

        tgt_rows = (
            db.query(ShippingProviderPricingMatrix)
            .filter(ShippingProviderPricingMatrix.group_id == target_group_id)
            .order_by(
                ShippingProviderPricingMatrix.min_kg.asc(),
                ShippingProviderPricingMatrix.max_kg.asc().nulls_last(),
                ShippingProviderPricingMatrix.id.asc(),
            )
            .all()
        )

        tgt_index: Dict[Tuple[Decimal, Optional[Decimal]], ShippingProviderPricingMatrix] = {
            range_key(r.min_kg, r.max_kg): r for r in tgt_rows
        }

        created: List[PricingMatrixOut] = []
        updated: List[PricingMatrixOut] = []
        skipped: List[PricingMatrixOut] = []
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
            for sr in src_rows:
                key = range_key(sr.min_kg, sr.max_kg)
                tr = tgt_index.get(key)

                new_mode = normalize_mode(sr.pricing_mode)
                new_flat = sr.flat_amount
                new_base = sr.base_amount
                new_rate = sr.rate_per_kg
                new_base_kg = getattr(sr, "base_kg", None)
                new_active = resolve_active(bool(sr.active))

                validate_payload_for_mode(new_mode, new_flat, new_base, new_rate, new_base_kg)

                if tr is None:
                    nr = ShippingProviderPricingMatrix(
                        group_id=target_group_id,
                        min_kg=sr.min_kg,
                        max_kg=sr.max_kg,
                        pricing_mode=new_mode,
                        flat_amount=new_flat,
                        base_amount=new_base,
                        rate_per_kg=new_rate,
                        base_kg=new_base_kg,
                        active=new_active,
                    )
                    db.add(nr)
                    try:
                        db.flush()
                    except IntegrityError as e:
                        db.rollback()
                        if conflict_policy == "abort":
                            handle_integrity_error(e)
                        failed.append(
                            {
                                "min_kg": float(sr.min_kg),
                                "max_kg": None if sr.max_kg is None else float(sr.max_kg),
                                "error": "integrity_error",
                                "detail": str(getattr(e, "orig", e)),
                            }
                        )
                        continue

                    db.refresh(nr)
                    tgt_index[key] = nr
                    created.append(as_pricing_matrix_out(nr))
                    continue

                if conflict_policy == "skip":
                    skipped.append(as_pricing_matrix_out(tr))
                    continue

                if conflict_policy == "abort":
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"Pricing matrix range conflict at "
                            f"min_kg={float(sr.min_kg)} "
                            f"max_kg={None if sr.max_kg is None else float(sr.max_kg)}"
                        ),
                    )

                tr.pricing_mode = new_mode
                tr.flat_amount = new_flat
                tr.base_amount = new_base
                tr.rate_per_kg = new_rate
                tr.base_kg = new_base_kg
                tr.active = new_active

                try:
                    db.flush()
                except IntegrityError as e:
                    db.rollback()
                    failed.append(
                        {
                            "id": tr.id,
                            "min_kg": float(tr.min_kg),
                            "max_kg": None if tr.max_kg is None else float(tr.max_kg),
                            "error": "integrity_error",
                            "detail": str(getattr(e, "orig", e)),
                        }
                    )
                    continue

                updated.append(as_pricing_matrix_out(tr))

            db.commit()
        except HTTPException:
            db.rollback()
            raise
        except IntegrityError as e:
            db.rollback()
            handle_integrity_error(e)

        summary = CopyPricingMatrixSummary(
            source_count=len(src_rows),
            created_count=len(created),
            updated_count=len(updated),
            skipped_count=len(skipped),
            failed_count=len(failed),
        )

        return CopyPricingMatrixOut(
            ok=True,
            target_group_id=target_group_id,
            source_group_id=payload.source_group_id,
            conflict_policy=conflict_policy,
            active_policy=active_policy,
            summary=summary,
            created=created,
            updated=updated,
            skipped=skipped,
            failed=failed,
        )
