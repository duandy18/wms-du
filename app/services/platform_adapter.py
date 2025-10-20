from abc import ABC, abstractmethod
from typing import Any, Dict, List


class PlatformAdapter(ABC):
    """统一平台事件适配接口，用于解耦多平台事件结构。"""

    platform: str

    @abstractmethod
    async def parse_event(self, raw_event: Dict[str, Any]) -> Dict[str, Any]:
        """将原始事件解析为标准化结构。"""
        ...

    @abstractmethod
    async def to_outbound_task(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """将解析后的事件映射到出库任务模型。"""
        ...


class PDDAdapter(PlatformAdapter):
    platform = "pdd"

    async def parse_event(self, raw_event: Dict[str, Any]) -> Dict[str, Any]:
        # TODO: 按 PDD 的字段规则解析
        return {"order_id": raw_event.get("order_sn"), "status": raw_event.get("status")}

    async def to_outbound_task(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        # TODO: 转换为系统标准出库任务
        return {"platform": self.platform, "ref": parsed["order_id"], "state": parsed["status"]}
