from __future__ import annotations

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.deps import get_db
from app.tms.permissions import check_config_perm
from app.tms.pricing.templates.repository import (
    build_template_stats,
    load_template_detail_or_404,
    serialize_template_out,
)
from app.tms.pricing.templates.schemas.template import TemplateDetailOut


def register_detail_routes(router: APIRouter) -> None:
    @router.get(
        "/templates/{template_id}",
        response_model=TemplateDetailOut,
        name="pricing_template_detail",
    )
    def get_template_detail(
        template_id: int = Path(..., ge=1),
        db: Session = Depends(get_db),
        user=Depends(get_current_user),
    ):
        check_config_perm(db, user, ["config.store.read"])

        row = load_template_detail_or_404(db, template_id=int(template_id))
        stats = build_template_stats(db, template_id=int(template_id))

        return TemplateDetailOut(
            ok=True,
            data=serialize_template_out(row, include_detail=True, stats=stats),
        )
