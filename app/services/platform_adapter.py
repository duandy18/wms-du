from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict

StandardEvent = Dict[str, Any]
RawEvent = Dict[str, Any]


class PlatformAdapter(ABC):
    platform: str

    @abstractmethod
    async def parse_event(self, raw_event: RawEvent) -> StandardEvent:
        """解析平台原始事件为标准结构（order_id/status/lines/raw）。"""
        ...

    @abstractmethod
    async def to_outbound_task(self, parsed: StandardEvent) -> Dict[str, Any]:
        """映射为业务入口任务（platform/ref/state/lines/payload）。"""
        ...


def _base_to_task(parsed: StandardEvent) -> Dict[str, Any]:
    """统一输出结构：ref=order_id，透传 lines 与原始 payload。"""
    return {
        "platform": parsed["platform"],
        "ref": parsed.get("order_id") or "",
        "state": parsed.get("status") or "",
        "lines": parsed.get("lines"),
        "payload": parsed.get("raw"),
    }


class PDDAdapter(PlatformAdapter):
    platform = "pdd"

    async def parse_event(self, raw_event: RawEvent) -> StandardEvent:
        return {
            "platform": self.platform,
            "order_id": raw_event.get("order_sn") or raw_event.get("order_id") or "",
            "status": raw_event.get("status") or "",
            "lines": raw_event.get("lines"),
            "raw": raw_event,
        }

    async def to_outbound_task(self, parsed: StandardEvent) -> Dict[str, Any]:
        return _base_to_task(parsed)


class TaobaoAdapter(PlatformAdapter):
    platform = "taobao"

    async def parse_event(self, raw_event: RawEvent) -> StandardEvent:
        # 常见字段：tid（订单号）、trade_status（状态）
        return {
            "platform": self.platform,
            "order_id": raw_event.get("tid") or raw_event.get("order_id") or "",
            "status": raw_event.get("trade_status") or raw_event.get("status") or "",
            "lines": raw_event.get("lines"),
            "raw": raw_event,
        }

    async def to_outbound_task(self, parsed: StandardEvent) -> Dict[str, Any]:
        return _base_to_task(parsed)


class JDAdapter(PlatformAdapter):
    platform = "jd"

    async def parse_event(self, raw_event: RawEvent) -> StandardEvent:
        # 常见字段：orderId（订单号）、orderStatus（状态）
        return {
            "platform": self.platform,
            "order_id": raw_event.get("orderId") or raw_event.get("order_id") or "",
            "status": raw_event.get("orderStatus") or raw_event.get("status") or "",
            "lines": raw_event.get("lines"),
            "raw": raw_event,
        }

    async def to_outbound_task(self, parsed: StandardEvent) -> Dict[str, Any]:
        return _base_to_task(parsed)
