# app/services/platform_adapter.py
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, List, Optional

StandardEvent = Dict[str, Any]
RawEvent = Dict[str, Any]
Task = Dict[str, Any]


class PlatformAdapter(ABC):
    platform: str

    @abstractmethod
    async def parse_event(self, raw: RawEvent) -> StandardEvent:
        ...

    @abstractmethod
    async def to_outbound_task(self, parsed: StandardEvent) -> Task:
        ...


def _base_to_task(parsed: StandardEvent) -> Task:
    return {
        "platform": parsed["platform"],
        "ref": parsed.get("order_id") or "",
        "state": parsed.get("status") or "",
        "lines": [],
        "shop_id": parsed.get("shop_id"),
        "payload": parsed.get("raw"),
    }


# ============================================================
# 行规范化工具
# ============================================================

_ItemIdKeys = ("item_id", "itemId", "sku_id", "skuId", "goods_id", "goodsId", "id")
_QtyKeys = ("qty", "quantity", "num", "count", "amount")
_LocIdKeys = ("location_id", "loc_id", "locationId", "warehouse_loc_id", "bin_id", "binId")


def _norm_int(val: Any, default: Optional[int] = None) -> Optional[int]:
    if val is None or val == "":
        return default
    try:
        return int(val)
    except Exception:
        try:
            return int(float(str(val)))
        except Exception:
            return default


def _first_present(d: Dict[str, Any], keys: Iterable[str]) -> Any:
    for k in keys:
        if k in d:
            return d[k]
    return None


def _normalize_lines_v2(
    lines: Any,
) -> tuple[List[Dict[str, int]], List[Dict[str, int]]]:
    """
    v2 规范化（新世界观）：

    返回：
    - clean_lines : [{item_id, qty}]
    - ship_lines  : [{item_id, qty, location_hint}]（仅当存在 location）
    """
    clean: List[Dict[str, int]] = []
    ship: List[Dict[str, int]] = []

    if not lines:
        return clean, ship
    if not isinstance(lines, list):
        lines = [lines]

    for raw in lines:
        if not isinstance(raw, dict):
            continue

        item = _norm_int(_first_present(raw, _ItemIdKeys))
        qty = _norm_int(_first_present(raw, _QtyKeys))
        loc = _norm_int(_first_present(raw, _LocIdKeys))

        if item is None or qty is None or qty <= 0:
            continue

        base = {"item_id": item, "qty": qty}
        clean.append(base)

        if loc is not None:
            ship.append({**base, "location_hint": loc})

    return clean, ship


# ------------------------------------------------------------
# LEGACY 工具函数（⚠️ 仍需保留合同）
# ------------------------------------------------------------

def _normalize_lines(lines: Any, *, need_location: bool = False) -> List[Dict[str, int]]:
    """
    legacy 规范化工具（历史合同）：

    - need_location=False → [{item_id, qty}]
    - need_location=True  → [{item_id, qty, location_id}]
    """
    out: List[Dict[str, int]] = []

    if not lines:
        return out
    if not isinstance(lines, list):
        lines = [lines]

    for raw in lines:
        if not isinstance(raw, dict):
            continue

        item = _norm_int(_first_present(raw, _ItemIdKeys))
        qty = _norm_int(_first_present(raw, _QtyKeys))
        loc = _norm_int(_first_present(raw, _LocIdKeys))

        if item is None or qty is None or qty <= 0:
            continue

        if need_location:
            if loc is None:
                continue
            out.append({"item_id": item, "qty": qty, "location_id": loc})
        else:
            out.append({"item_id": item, "qty": qty})

    return out


# ============================================================
# 各平台 Adapter（新世界观）
# ============================================================

class PDDAdapter(PlatformAdapter):
    platform = "pdd"

    async def parse_event(self, raw: RawEvent) -> StandardEvent:
        return {
            "platform": self.platform,
            "order_id": raw.get("order_sn") or raw.get("order_id") or "",
            "status": raw.get("status") or "",
            "lines": raw.get("lines"),
            "shop_id": raw.get("shop_id") or "",
            "raw": raw,
        }

    async def to_outbound_task(self, parsed: StandardEvent) -> Task:
        t = _base_to_task(parsed)

        clean, ship = _normalize_lines_v2(parsed.get("lines"))

        t["lines"] = clean
        t["ship_lines"] = ship   # ✅ 新世界观（无 legacy）

        return t


class TaobaoAdapter(PDDAdapter):
    platform = "taobao"


class TmallAdapter(PDDAdapter):
    platform = "tmall"


class JDAdapter(PDDAdapter):
    platform = "jd"


class DouyinAdapter(PDDAdapter):
    platform = "douyin"


class XHSAdapter(PDDAdapter):
    platform = "xhs"
