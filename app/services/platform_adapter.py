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
# 行规范化工具（终态：不解析、不携带 location）
# ============================================================

_ItemIdKeys = ("item_id", "itemId", "sku_id", "skuId", "goods_id", "goodsId", "id")
_QtyKeys = ("qty", "quantity", "num", "count", "amount")


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


def _normalize_lines_v2(lines: Any) -> List[Dict[str, int]]:
    """
    终态 v2 规范化：

    返回：[{item_id, qty}]

    约束：
    - 不兼容 legacy_location / bin_id 等任何 location 维度（忽略，不输出，不解析）。
    """
    clean: List[Dict[str, int]] = []

    if not lines:
        return clean
    if not isinstance(lines, list):
        lines = [lines]

    for raw in lines:
        if not isinstance(raw, dict):
            continue

        item = _norm_int(_first_present(raw, _ItemIdKeys))
        qty = _norm_int(_first_present(raw, _QtyKeys))

        if item is None or qty is None or qty <= 0:
            continue

        clean.append({"item_id": int(item), "qty": int(qty)})

    return clean


# ============================================================
# 各平台 Adapter（终态）
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
        t["lines"] = _normalize_lines_v2(parsed.get("lines"))
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
