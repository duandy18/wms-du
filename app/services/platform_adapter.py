from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict

StandardEvent = Dict[str, Any]
RawEvent = Dict[str, Any]


class PlatformAdapter(ABC):
    """统一平台事件适配接口：将不同平台的原始事件 → 标准事件结构。"""

    platform: str

    @abstractmethod
    async def parse_event(self, raw_event: RawEvent) -> StandardEvent:
        """解析平台原始事件为标准结构。"""
        ...

    @abstractmethod
    async def to_outbound_task(self, parsed: StandardEvent) -> Dict[str, Any]:
        """把标准事件映射为系统的出库任务输入结构。"""
        ...


def _base_to_task(parsed: StandardEvent) -> Dict[str, Any]:
    """通用映射：透传 lines（若调用方在 raw 中提供），并保留原始 payload。"""
    return {
        "platform": parsed["platform"],
        "ref": parsed["order_id"],
        "state": parsed["status"],
        "lines": parsed.get("lines"),           # ← 透传
        "payload": parsed.get("raw"),
    }


# == PDD ==
class PDDAdapter(PlatformAdapter):
    platform = "pdd"

    async def parse_event(self, raw_event: RawEvent) -> StandardEvent:
        return {
            "platform": self.platform,
            "order_id": raw_event.get("order_sn"),
            "status": raw_event.get("status"),
            "lines": raw_event.get("lines"),    # ← 透传
            "raw": raw_event,
        }

    async def to_outbound_task(self, parsed: StandardEvent) -> Dict[str, Any]:
        return _base_to_task(parsed)


# == TAOBAO ==
class TaobaoAdapter(PlatformAdapter):
    platform = "taobao"

    async def parse_event(self, raw_event: RawEvent) -> StandardEvent:
        return {
            "platform": self.platform,
            "order_id": raw_event.get("tid"),
            "status": raw_event.get("trade_status"),
            "lines": raw_event.get("lines"),
            "raw": raw_event,
        }

    async def to_outbound_task(self, parsed: StandardEvent) -> Dict[str, Any]:
        return _base_to_task(parsed)


# == JD ==
class JDAdapter(PlatformAdapter):
    platform = "jd"

    async def parse_event(self, raw_event: RawEvent) -> StandardEvent:
        return {
            "platform": self.platform,
            "order_id": raw_event.get("orderId"),
            "status": raw_event.get("orderStatus"),
            "lines": raw_event.get("lines"),
            "raw": raw_event,
        }

    async def to_outbound_task(self, parsed: StandardEvent) -> Dict[str, Any]:
        return _base_to_task(parsed)
