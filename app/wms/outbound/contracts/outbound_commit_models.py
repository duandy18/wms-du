# app/wms/outbound/contracts/outbound_commit_models.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from app.wms.stock.services.stock_adjust.batch_keys import norm_batch_code


@dataclass(frozen=True)
class ShipLine:
    item_id: int
    warehouse_id: int
    qty: int
    batch_code: Optional[str] = None


def coerce_line(raw: Mapping[str, Any] | ShipLine) -> ShipLine:
    if isinstance(raw, ShipLine):
        return ShipLine(
            item_id=int(raw.item_id),
            warehouse_id=int(raw.warehouse_id),
            qty=int(raw.qty),
            batch_code=norm_batch_code(raw.batch_code),
        )

    item_id = int(raw["item_id"])
    warehouse_id = int(raw["warehouse_id"])
    qty = int(raw["qty"])
    batch_code = norm_batch_code(raw.get("batch_code"))

    return ShipLine(
        item_id=item_id,
        warehouse_id=warehouse_id,
        qty=qty,
        batch_code=batch_code,
    )


def problem_error_code_from_http_exc_detail(detail: Any) -> Optional[str]:
    if detail is None:
        return None

    if isinstance(detail, str):
        s = detail.strip()
        return s or None

    if isinstance(detail, Mapping):
        for key in ("error_code", "code", "type"):
            val = detail.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()

        details = detail.get("details")
        if isinstance(details, list):
            for item in details:
                if isinstance(item, Mapping):
                    for key in ("error_code", "code", "type"):
                        val = item.get(key)
                        if isinstance(val, str) and val.strip():
                            return val.strip()

        return None

    return None


__all__ = [
    "ShipLine",
    "coerce_line",
    "norm_batch_code",
    "problem_error_code_from_http_exc_detail",
]
