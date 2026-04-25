# app/shipping_assist/shipment/waybill_gateway_fake.py
from __future__ import annotations

from .waybill_service import WaybillProvider, WaybillRequest, WaybillResult


class FakeWaybillGateway(WaybillProvider):
    async def request_waybill(self, req: WaybillRequest) -> WaybillResult:
        tracking = f"P{int(req.shipping_provider_id)}-{req.ext_order_no}-{id(req) % 10000}"

        template_url = (
            "http://cloudprint.cainiao.com/cloudprint/template/getStandardTemplate.json"
            "?template_id=STANDARD_TEST"
        )

        sender_raw = req.sender if isinstance(req.sender, dict) else {}
        sender_phone = str(sender_raw.get("mobile") or sender_raw.get("phone") or "").strip()

        print_data = {
            "waybillCode": tracking,
            "recipient": req.receiver,
            "sender": {
                "name": sender_raw.get("name"),
                "phone": sender_phone or None,
                "address": {
                    "province": sender_raw.get("province"),
                    "city": sender_raw.get("city"),
                    "district": sender_raw.get("district"),
                    "detail": sender_raw.get("address"),
                },
            },
            "routingInfo": {},
            "shippingOption": {
                "code": "STANDARD",
                "services": {},
            },
        }

        return WaybillResult(
            ok=True,
            tracking_no=tracking,
            print_data=print_data,
            template_url=template_url,
            raw={"mock": True},
            source="PLATFORM_FAKE",
        )
