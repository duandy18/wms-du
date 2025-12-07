# app/services/waybill_service.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class WaybillRequest:
    """
    平台面单请求统一结构：

    - provider_code: 快递公司编码（ZTO/JT/SF...）
    - platform: 平台（PDD / JD / ...）
    - shop_id: 店铺 ID
    - ext_order_no: 平台订单号
    - receiver: 收件人信息
    - cargo: 货物信息（重量/体积/品名等）
    - extras: 任意扩展字段
    """

    provider_code: str
    platform: str
    shop_id: str
    ext_order_no: str

    receiver: Dict[str, Any]
    cargo: Dict[str, Any]
    extras: Dict[str, Any]


@dataclass
class WaybillResult:
    ok: bool
    tracking_no: Optional[str] = None

    # 面单内容（可选，未来接真实平台的 PDF/ZPL）
    label_bytes: Optional[bytes] = None
    label_format: Optional[str] = None  # "PDF" / "PNG" / "ZPL"

    error_code: Optional[str] = None
    error_message: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


class WaybillService:
    """
    平台面单服务抽象层（当前为 Fake 实现）：

    未来你可以有多种实现：
      - PddWaybillClient
      - JdWaybillClient
      - KdnWaybillClient（快递鸟）
    现在先返回一个 fake tracking_no，方便前后端联调。
    """

    async def request_waybill(self, req: WaybillRequest) -> WaybillResult:
        # TODO: 未来根据 platform/provider_code 路由到具体平台 SDK
        tracking = f"{req.provider_code}-{req.ext_order_no}"

        raw: Dict[str, Any] = {
            "platform": req.platform,
            "shop_id": req.shop_id,
            "ext_order_no": req.ext_order_no,
            "provider_code": req.provider_code,
            "receiver": req.receiver,
            "cargo": req.cargo,
            "extras": req.extras,
            "fake": True,
        }

        return WaybillResult(
            ok=True,
            tracking_no=tracking,
            label_bytes=None,
            label_format=None,
            raw=raw,
        )
