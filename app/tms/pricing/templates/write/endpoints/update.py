from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.user.deps.auth import get_current_user
from app.db.deps import get_db
from app.tms.permissions import check_config_perm
from app.tms.pricing.templates.repository import (
    build_template_capabilities,
    build_template_stats,
    is_template_bound,
    load_template_or_404,
    serialize_template_out,
)
from app.tms.pricing.templates.contracts.template import (
    TemplateDetailOut,
    TemplateUpdateIn,
)


def _norm_nonempty(value: str | None, field_name: str) -> str:
    v = str(value or "").strip()
    if not v:
        raise HTTPException(status_code=422, detail=f"{field_name} must be non-empty")
    return v


def _ensure_template_metadata_editable(
    *,
    template,
    bound: bool,
    changing_structure_contract: bool,
    changing_name_only: bool,
    db: Session,
) -> None:
    status = str(template.status)
    validation_status = str(template.validation_status)

    if status != "draft":
        raise HTTPException(
            status_code=400,
            detail="Only draft template can be modified",
        )
    if validation_status == "passed":
        raise HTTPException(
            status_code=400,
            detail="Validated template cannot be modified; clone a new draft to edit",
        )
    if bound:
        raise HTTPException(
            status_code=409,
            detail="pricing_template is bound; unbind it before editing",
        )

    stats = build_template_stats(db, template_id=int(template.id))
    caps = build_template_capabilities(template=template, stats=stats)

    if (
        changing_structure_contract
        and caps.readonly_reason == "cloned_template_structure_locked"
    ):
        raise HTTPException(
            status_code=400,
            detail="Cloned template cannot modify expected ranges/groups; create a new template if you need a different structure",
        )

    if changing_name_only:
        return


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

        metadata_changed = False

        changing_name = "name" in data
        changing_expected_counts = (
            "expected_ranges_count" in data or "expected_groups_count" in data
        )

        if changing_name or changing_expected_counts:
            _ensure_template_metadata_editable(
                template=row,
                bound=bound,
                changing_structure_contract=changing_expected_counts,
                changing_name_only=(changing_name and not changing_expected_counts),
                db=db,
            )

            if changing_name:
                row.name = _norm_nonempty(data.get("name"), "name")
                metadata_changed = True

            if "expected_ranges_count" in data:
                row.expected_ranges_count = int(data["expected_ranges_count"])
                metadata_changed = True

            if "expected_groups_count" in data:
                row.expected_groups_count = int(data["expected_groups_count"])
                metadata_changed = True

        if metadata_changed:
            row.validation_status = "not_validated"

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
