from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict

StandardEvent = Dict[str, Any]
RawEvent = Dict[str, Any]


class PlatformAdapter(ABC):
    platform: str

    @abstractmethod
    async def parse_event(self, raw: RawEvent) -> StandardEvent:
        """解析平台原始事件为标准结构（order_id/status/lines/shop_id/raw）。"""
        ...

    @abstractmethod
    async def to_outbound_task(self, parsed: StandardEvent) -> Dict[str, Any]:
        """映射为业务入口任务（platform/ref/state/lines/shop_id/payload）。"""
        ...


def _base_to_task(parsed: StandardEvent) -> Dict[str, Any]:
    """统一输出结构：ref=order_id，透传 lines 与原始 payload，并带 shop_id。"""
    return {
        "platform": parsed["platform"],
        "ref": parsed.get("order_id") or "",
        "state": parsed.get("status") or "",
        "lines": parsed.get("lines"),
        "shop_id": parsed.get("shop_id"),
        "payload": parsed.get("raw"),
    }


def _shop_id_of(raw: RawEvent) -> str:
    """从通用字段尽力提取 shop_id。"""
    return str(
        raw.get("shop_id")
        or raw.get("shop")
        or raw.get("store_id")
        or raw.get("seller_id")
        or raw.get("author_id")
        or raw.get("shopId")
        or ""
    )


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

    async def to_outbound_task(self, parsed: StandardEvent) -> Dict[str, Any]:
        return _base_to_task(parsed)


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

    async def to_outbound_task(self, parsed: StandardEvent) -> Dict[str, Any]:
        return _base_to_task(parsed)


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

    async def to_outbound_task(self, parsed: StandardEvent) -> Dict[str, Any]:
        return _base_to_task(parsed)


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

    async def to_outbound_task(self, parsed: StandardEvent) -> Dict[str, Any]:
        return _base_to_task(parsed)


# ---------- Douyin ----------
class DouyinAdapter(PlatformAdapter):
    platform = "douyin"

    async def parse_event(self, raw: RawEvent) -> StandardEvent:
        # 常见：order_id / status（或 trade_status）、lines、自定义 shop_id 字段
        return {
            "platform": self.platform,
            "order_id": raw.get("order_id") or raw.get("orderId") or raw.get("tid") or "",
            "status": raw.get("status") or raw.get("trade_status") or "",
            "lines": raw.get("lines"),
            "shop_id": _shop_id_of(raw),
            "raw": raw,
        }

    async def to_outbound_task(self, parsed: StandardEvent) -> Dict[str, Any]:
        return _base_to_task(parsed)


# ---------- Xiaohongshu（小红书） ----------
class XHSAdapter(PlatformAdapter):
    platform = "xhs"

    async def parse_event(self, raw: RawEvent) -> StandardEvent:
        # 常见：order_id / status、lines，店铺 ID 可能在 seller_id/store_id
        return {
            "platform": self.platform,
            "order_id": raw.get("order_id") or raw.get("orderId") or raw.get("tid") or "",
            "status": raw.get("status") or raw.get("trade_status") or "",
            "lines": raw.get("lines"),
            "shop_id": _shop_id_of(raw),
            "raw": raw,
        }

    async def to_outbound_task(self, parsed: StandardEvent) -> Dict[str, Any]:
        return _base_to_task(parsed)
