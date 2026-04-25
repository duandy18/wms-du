# app/shipping_assist/quote/calc_quote.py
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from .calc_quote_level3 import calc_quote_level3
from .context_from_template import load_template_quote_context
from .types import Dest

JsonObject = Dict[str, object]


def calc_quote(
    db: Session,
    template_id: int,
    warehouse_id: int,
    dest: Dest,
    real_weight_kg: float,
    dims_cm: Optional[Tuple[float, float, float]],
    flags: Optional[List[str]],
) -> JsonObject:
    _ = warehouse_id

    ctx = load_template_quote_context(
        db=db,
        template_id=int(template_id),
    )

    return calc_quote_level3(
        ctx=ctx,
        dest=dest,
        real_weight_kg=real_weight_kg,
        dims_cm=dims_cm,
        flags=flags,
    )
