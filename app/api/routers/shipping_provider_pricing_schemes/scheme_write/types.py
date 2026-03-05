from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class SchemeSegmentActivePatchIn(BaseModel):
    active: bool


class SchemeDefaultSegmentTemplateIn(BaseModel):
    template_id: Optional[int] = None
