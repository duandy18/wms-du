# app/shipping_assist/shipment/waybill_service.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol


@dataclass(frozen=True)
class WaybillRequest:
    shipping_provider_id: int
    provider_code: Optional[str]
    company_code: Optional[str]
    customer_code: Optional[str]

    platform: str
    shop_id: str
    ext_order_no: str

    sender: Optional[Dict[str, Any]]
    receiver: Dict[str, Any]
    cargo: Dict[str, Any]
    extras: Dict[str, Any]


@dataclass(frozen=True)
class WaybillResult:
    ok: bool
    tracking_no: Optional[str] = None

    # 打印合同：对外保持不变
    print_data: Optional[Dict[str, Any]] = None
    template_url: Optional[str] = None

    # 错误与调试信息
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None

    # 来源标记：用于审计 / 台账，不再由上层硬编码
    source: Optional[str] = None


class WaybillProvider(Protocol):
    async def request_waybill(self, req: WaybillRequest) -> WaybillResult:
        ...
