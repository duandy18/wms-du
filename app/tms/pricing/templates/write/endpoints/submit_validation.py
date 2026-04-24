from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.user.deps.auth import get_current_user
from app.db.deps import get_db
from app.tms.pricing.templates.models.shipping_provider_pricing_template_validation_record import (
    ShippingProviderPricingTemplateValidationRecord,
)
from app.tms.permissions import check_config_perm
from app.tms.pricing.templates.module_resources_shared import (
    validate_template_ready_for_binding,
)
from app.tms.pricing.templates.repository import (
    build_template_capabilities,
    build_template_stats,
    load_template_or_404,
    serialize_template_out,
)
from app.tms.pricing.templates.contracts.template import TemplateDetailOut


class TemplateSubmitValidationIn(BaseModel):
    confirm_validated: bool


def register_submit_validation_routes(router: APIRouter) -> None:
    @router.post(
        "/templates/{template_id}/submit-validation",
        response_model=TemplateDetailOut,
        name="pricing_template_submit_validation",
    )
    def submit_validation(
        template_id: int = Path(..., ge=1),
        payload: TemplateSubmitValidationIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_config_perm(db, user, ["config.store.write"])

        if payload.confirm_validated is not True:
            raise HTTPException(status_code=400, detail="confirm_validated must be true")

        row = load_template_or_404(db, template_id=int(template_id))
        stats = build_template_stats(db, template_id=int(row.id))
        caps = build_template_capabilities(template=row, stats=stats)

        if not caps.can_submit_validation:
            if caps.readonly_reason == "archived_template":
                raise HTTPException(
                    status_code=400,
                    detail="Archived template cannot be validated; clone a new draft to continue",
                )
            if caps.readonly_reason == "validated_template":
                raise HTTPException(
                    status_code=400,
                    detail="Template already validated",
                )
            raise HTTPException(
                status_code=400,
                detail="Template cannot submit validation in current state",
            )

        validate_template_ready_for_binding(db, template_id=int(row.id))

        record = ShippingProviderPricingTemplateValidationRecord(
            template_id=int(row.id),
            operator_user_id=int(user.id),
        )
        db.add(record)

        row.validation_status = "passed"

        db.commit()
        db.refresh(row)

        stats = build_template_stats(db, template_id=int(row.id))

        return TemplateDetailOut(
            ok=True,
            data=serialize_template_out(row, include_detail=False, stats=stats),
        )
