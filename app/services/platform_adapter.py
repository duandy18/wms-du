from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, List, Optional

StandardEvent = Dict[str, Any]
RawEvent = Dict[str, Any]
Task = Dict[str, Any]


# ============================================================
#                    基类与通用工具
# ============================================================


class PlatformAdapter(ABC):
    platform: str

    @abstractmethod
    async def parse_event(self, raw: RawEvent) -> StandardEvent:
        """
        解析“平台原始事件”为标准事件：
        {
          platform,        # 平台标识（小写）
          order_id,        # 平台侧订单号/唯一引用
          status,          # 平台状态（如 PAID/SHIPPED/CANCELED ...）
          lines,           # 原始行列表
          shop_id,         # 店铺标识
          raw              # 原始载荷透传
        }
        """
        ...

    @abstractmethod
    async def to_outbound_task(self, parsed: StandardEvent) -> Task:
        """
        将标准事件映射为“业务任务”：
        {
          platform, ref, state,
          lines: [{item_id, qty}[, {location_id}...]],
          shop_id, payload
        }
        """
        ...


def _base_to_task(parsed: StandardEvent) -> Task:
    """统一输出骨架：ref=order_id，透传 lines / raw / shop_id。"""
    return {
        "platform": parsed["platform"],
        "ref": parsed.get("order_id") or "",
        "state": parsed.get("status") or "",
        "lines": parsed.get("lines"),
        "shop_id": parsed.get("shop_id"),
        "payload": parsed.get("raw"),
    }


def _shop_id_of(raw: RawEvent) -> str:
    """从常见字段提取 shop_id。"""
    return str(
        raw.get("shop_id")
        or raw.get("shop")
        or raw.get("store_id")
        or raw.get("seller_id")
        or raw.get("author_id")
        or raw.get("shopId")
        or ""
    )


# --------------------- 行规范化：item/qty[/location] ---------------------

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


def _normalize_lines(lines: Any, *, need_location: bool = False) -> List[Dict[str, int]]:
    """
    将多形态 lines 规整为 [{item_id, qty}[, location_id]]。
    - 当 need_location=True 时，仅保留含 location_id 的行（用于 SHIP 尝试直达）；
    - 当 need_location=False 时，忽略 location_id，仅保留 item/qty（用于 RESERVE/CANCEL）。
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

        if item is None or qty is None:
            continue
        if qty <= 0:
            continue

        if need_location:
            if loc is None:
                # 缺库位：本行无法用于发货，跳过（让上游严格校验）
                continue
            out.append({"item_id": item, "location_id": loc, "qty": qty})
        else:
            out.append({"item_id": item, "qty": qty})

    return out


# ============================================================
#                        平台适配器
# ============================================================


# ---------- PDD ----------
class PDDAdapter(PlatformAdapter):
    platform = "pdd"

    async def parse_event(self, raw: RawEvent) -> StandardEvent:
        return {
            "platform": self.platform,
            "order_id": raw.get("order_sn") or raw.get("order_id") or "",
            "status": raw.get("status") or "",
            "lines": raw.get("lines"),
            "shop_id": _shop_id_of(raw),
            "raw": raw,
        }

    async def to_outbound_task(self, parsed: StandardEvent) -> Task:
        t = _base_to_task(parsed)
        # PDD 常见：已付/取消无库位，发货可能带库位（若对接了 WMS）
        # 这里仅规范化行；是否需要 location_id 由上游按状态决定
        t["lines"] = _normalize_lines(parsed.get("lines"))
        t["ship_lines"] = _normalize_lines(parsed.get("lines"), need_location=True)
        return t


# ---------- Taobao ----------
class TaobaoAdapter(PlatformAdapter):
    platform = "taobao"

    async def parse_event(self, raw: RawEvent) -> StandardEvent:
        return {
            "platform": self.platform,
            "order_id": raw.get("tid") or raw.get("order_id") or "",
            "status": raw.get("trade_status") or raw.get("status") or "",
            "lines": raw.get("lines"),
            "shop_id": _shop_id_of(raw),
            "raw": raw,
        }

    async def to_outbound_task(self, parsed: StandardEvent) -> Task:
        t = _base_to_task(parsed)
        t["lines"] = _normalize_lines(parsed.get("lines"))
        t["ship_lines"] = _normalize_lines(parsed.get("lines"), need_location=True)
        return t


# ---------- Tmall ----------
class TmallAdapter(PlatformAdapter):
    platform = "tmall"

    async def parse_event(self, raw: RawEvent) -> StandardEvent:
        return {
            "platform": self.platform,
            "order_id": raw.get("tid") or raw.get("order_id") or "",
            "status": raw.get("trade_status") or raw.get("status") or "",
            "lines": raw.get("lines"),
            "shop_id": _shop_id_of(raw),
            "raw": raw,
        }

    async def to_outbound_task(self, parsed: StandardEvent) -> Task:
        t = _base_to_task(parsed)
        t["lines"] = _normalize_lines(parsed.get("lines"))
        t["ship_lines"] = _normalize_lines(parsed.get("lines"), need_location=True)
        return t


# ---------- JD ----------
class JDAdapter(PlatformAdapter):
    platform = "jd"

    async def parse_event(self, raw: RawEvent) -> StandardEvent:
        return {
            "platform": self.platform,
            "order_id": raw.get("orderId") or raw.get("order_id") or "",
            "status": raw.get("orderStatus") or raw.get("status") or "",
            "lines": raw.get("lines"),
            "shop_id": _shop_id_of(raw),
            "raw": raw,
        }

    async def to_outbound_task(self, parsed: StandardEvent) -> Task:
        t = _base_to_task(parsed)
        t["lines"] = _normalize_lines(parsed.get("lines"))
        t["ship_lines"] = _normalize_lines(parsed.get("lines"), need_location=True)
        return t


# ---------- Douyin ----------
class DouyinAdapter(PlatformAdapter):
    platform = "douyin"

    async def parse_event(self, raw: RawEvent) -> StandardEvent:
        return {
            "platform": self.platform,
            "order_id": raw.get("order_id") or raw.get("orderId") or raw.get("tid") or "",
            "status": raw.get("status") or raw.get("trade_status") or "",
            "lines": raw.get("lines"),
            "shop_id": _shop_id_of(raw),
            "raw": raw,
        }

    async def to_outbound_task(self, parsed: StandardEvent) -> Task:
        t = _base_to_task(parsed)
        t["lines"] = _normalize_lines(parsed.get("lines"))
        t["ship_lines"] = _normalize_lines(parsed.get("lines"), need_location=True)
        return t


# ---------- Xiaohongshu（小红书） ----------
class XHSAdapter(PlatformAdapter):
    platform = "xhs"

    async def parse_event(self, raw: RawEvent) -> StandardEvent:
        return {
            "platform": self.platform,
            "order_id": raw.get("order_id") or raw.get("orderId") or raw.get("tid") or "",
            "status": raw.get("status") or raw.get("trade_status") or "",
            "lines": raw.get("lines"),
            "shop_id": _shop_id_of(raw),
            "raw": raw,
        }

    async def to_outbound_task(self, parsed: StandardEvent) -> Task:
        t = _base_to_task(parsed)
        t["lines"] = _normalize_lines(parsed.get("lines"))
        t["ship_lines"] = _normalize_lines(parsed.get("lines"), need_location=True)
        return t
