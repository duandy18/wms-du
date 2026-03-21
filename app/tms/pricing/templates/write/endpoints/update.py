from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.deps import get_db
from app.tms.permissions import check_config_perm
from app.tms.pricing.templates.repository import (
    build_template_stats,
    is_template_bound,
    load_template_or_404,
    serialize_template_out,
)
from app.tms.pricing.templates.schemas.template import (
    TemplateDetailOut,
    TemplateUpdateIn,
)


def _norm_nonempty(value: str | None, field_name: str) -> str:
    v = str(value or "").strip()
    if not v:
        raise HTTPException(status_code=422, detail=f"{field_name} must be non-empty")
    return v


def register_update_routes(router: APIRouter) -> None:
    @router.patch(
        "/templates/{template_id}",
        response_model=TemplateDetailOut,
        name="pricing_template_update",
    )
    def update_template(
        template_id: int = Path(..., ge=1),
        payload: TemplateUpdateIn = ...,
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_config_perm(db, user, ["config.store.write"])

        row = load_template_or_404(db, template_id=int(template_id))
        data = payload.model_dump(exclude_unset=True)
        bound = is_template_bound(db, template_id=int(template_id))

        if "name" in data:
            if str(row.status) != "draft":
                raise HTTPException(
                    status_code=400,
                    detail="Only draft template can be modified",
                )
            if bound:
                raise HTTPException(
                    status_code=409,
                    detail="pricing_template is bound; unbind it before editing",
                )
            row.name = _norm_nonempty(data.get("name"), "name")
            row.validation_status = "not_validated"

        if "validation_status" in data:
            if str(row.status) != "draft":
                raise HTTPException(
                    status_code=400,
                    detail="Only draft template can update validation_status",
                )
            if bound:
                raise HTTPException(
                    status_code=409,
                    detail="pricing_template is bound; unbind it before updating validation_status",
                )
            row.validation_status = str(data.get("validation_status"))

        if "status" in data:
            next_status = str(data.get("status"))
            if next_status == "archived" and bound:
                raise HTTPException(
                    status_code=409,
                    detail="pricing_template is bound; unbind it before archiving",
                )
            row.status = next_status
            if next_status == "archived":
                row.archived_at = datetime.now(timezone.utc)
            else:
                row.archived_at = None

        db.commit()
        db.refresh(row)

        stats = build_template_stats(db, template_id=int(row.id))

        return TemplateDetailOut(
            ok=True,
            data=serialize_template_out(row, include_detail=False, stats=stats),
        )
