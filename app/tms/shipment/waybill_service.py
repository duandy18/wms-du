# app/tms/shipment/waybill_service.py
# 分拆说明：
# - 本文件从 app/services/waybill_service.py 迁入 app/tms/shipment；
# - 目标是把 Shipment 面单申请实现收回 TMS 主域，消除 services 层运输兼容壳；
# - 当前仍为 fake 实现，后续可在此处切换真实平台 SDK / 网关适配。
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class WaybillRequest:
    """
    平台面单请求统一结构（终态：强身份以 shipping_provider_id 为准）：

    - shipping_provider_id: 承运商/网点 ID（强身份）
    - provider_code: 快递公司编码（冗余展示/对接用，可选）
    - platform: 平台（PDD / JD / ...）
    - shop_id: 店铺 ID
    - ext_order_no: 平台订单号
    - receiver: 收件人信息
    - cargo: 货物信息（重量/体积/品名等）
    - extras: 任意扩展字段
    """

    shipping_provider_id: int
    provider_code: Optional[str]
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
    平台面单服务抽象层（当前为 Fake 实现）

    终态合同：
    - 强身份：shipping_provider_id
    - provider_code 仅作为冗余展示/对接字段（如某些平台需要）
    """

    async def request_waybill(self, req: WaybillRequest) -> WaybillResult:
        # TODO: 未来根据 platform + shipping_provider_id 路由到具体平台 SDK
        tracking = f"P{int(req.shipping_provider_id)}-{req.ext_order_no}"

        raw: Dict[str, Any] = {
            "platform": req.platform,
            "shop_id": req.shop_id,
            "ext_order_no": req.ext_order_no,
            "shipping_provider_id": int(req.shipping_provider_id),
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
