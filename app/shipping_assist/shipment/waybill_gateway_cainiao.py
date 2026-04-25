# app/shipping_assist/shipment/waybill_gateway_cainiao.py
from __future__ import annotations

import json
from typing import Any

from .contracts import ShipmentApplicationError
from .waybill_service import WaybillProvider, WaybillRequest, WaybillResult
from .waybill_settings import WaybillTopSettings
from .waybill_top_client import TopApiClient


class CainiaoTopWaybillGateway(WaybillProvider):
    """
    真实菜鸟 / TOP 面单 provider 第一刀：
    - 已接入 TOP 签名与公共请求链路
    - 已预留 waybill.ii.get 调用入口
    - 当前阶段把 shipment 已明确提供的真相字段接进来：
      - provider_code(cp_code)
      - company_code
      - customer_code
      - sender
      - receiver
      - cargo(weight)
    - 当前已完成第一版 payload builder 与响应 mapper；
      在未确认线上请求开关前，仍不直接发起 TOP 请求。
    """

    TOP_METHOD = "cainiao.waybill.ii.get"

    ORDER_CHANNEL_MAP = {
        "PDD": "PIN_DUO_DUO",
        "TB": "TB",
        "TM": "TM",
        "JD": "JD",
        "YZ": "YOU_ZAN",
        "YOUZAN": "YOU_ZAN",
    }

    def __init__(self, settings: WaybillTopSettings) -> None:
        self.settings = settings
        self.client = TopApiClient(settings)

    async def request_waybill(self, req: WaybillRequest) -> WaybillResult:
        provider_code = str(req.provider_code or "").strip().upper()
        if not provider_code:
            raise ShipmentApplicationError(
                status_code=409,
                code="WAYBILL_CAINIAO_PROVIDER_CODE_REQUIRED",
                message="provider_code is required for cainiao top waybill request",
            )

        company_code = str(req.company_code or "").strip().upper()
        if not company_code:
            raise ShipmentApplicationError(
                status_code=409,
                code="WAYBILL_CAINIAO_COMPANY_CODE_REQUIRED",
                message="company_code is required for cainiao top waybill request",
            )

        customer_code = str(req.customer_code or "").strip()
        if not customer_code:
            raise ShipmentApplicationError(
                status_code=409,
                code="WAYBILL_CAINIAO_CUSTOMER_CODE_REQUIRED",
                message="customer_code is required for cainiao top waybill request",
            )

        sender_raw = req.sender if isinstance(req.sender, dict) else {}
        sender_name = str(sender_raw.get("name") or "").strip()
        sender_mobile = str(sender_raw.get("mobile") or "").strip()
        sender_phone = str(sender_raw.get("phone") or "").strip()
        sender_province = str(sender_raw.get("province") or "").strip()
        sender_city = str(sender_raw.get("city") or "").strip()
        sender_district = str(sender_raw.get("district") or "").strip()
        sender_address = str(sender_raw.get("address") or "").strip()

        if not sender_name:
            raise ShipmentApplicationError(
                status_code=409,
                code="WAYBILL_CAINIAO_SENDER_NAME_REQUIRED",
                message="sender name is required for cainiao top waybill request",
            )
        if not sender_mobile and not sender_phone:
            raise ShipmentApplicationError(
                status_code=409,
                code="WAYBILL_CAINIAO_SENDER_CONTACT_REQUIRED",
                message="sender mobile or phone is required for cainiao top waybill request",
            )
        if not sender_province or not sender_city or not sender_address:
            raise ShipmentApplicationError(
                status_code=409,
                code="WAYBILL_CAINIAO_SENDER_ADDRESS_REQUIRED",
                message="sender province/city/address is required for cainiao top waybill request",
            )

        receiver = req.receiver if isinstance(req.receiver, dict) else {}
        cargo = req.cargo if isinstance(req.cargo, dict) else {}

        receiver_name = str(receiver.get("name") or "").strip()
        receiver_phone = str(receiver.get("phone") or "").strip()
        province = str(receiver.get("province") or "").strip()
        city = str(receiver.get("city") or "").strip()
        district = str(receiver.get("district") or "").strip()
        detail = str(receiver.get("detail") or "").strip()

        if not receiver_name:
            raise ShipmentApplicationError(
                status_code=409,
                code="WAYBILL_CAINIAO_RECEIVER_NAME_REQUIRED",
                message="receiver name is required for cainiao top waybill request",
            )
        if not receiver_phone:
            raise ShipmentApplicationError(
                status_code=409,
                code="WAYBILL_CAINIAO_RECEIVER_PHONE_REQUIRED",
                message="receiver phone is required for cainiao top waybill request",
            )
        if not province or not city or not detail:
            raise ShipmentApplicationError(
                status_code=409,
                code="WAYBILL_CAINIAO_RECEIVER_ADDRESS_REQUIRED",
                message="receiver province/city/detail is required for cainiao top waybill request",
            )

        weight_kg = cargo.get("weight_kg")
        if weight_kg is None or float(weight_kg) <= 0:
            raise ShipmentApplicationError(
                status_code=409,
                code="WAYBILL_CAINIAO_WEIGHT_REQUIRED",
                message="weight_kg is required for cainiao top waybill request",
            )

        self._build_waybill_cloud_print_apply_new_cols(
            req=req,
            company_code=company_code,
            provider_code=provider_code,
            customer_code=customer_code,
            sender_name=sender_name,
            sender_mobile=sender_mobile,
            sender_phone=sender_phone,
            sender_province=sender_province,
            sender_city=sender_city,
            sender_district=sender_district,
            sender_address=sender_address,
            receiver_name=receiver_name,
            receiver_phone=receiver_phone,
            province=province,
            city=city,
            district=district,
            detail=detail,
            weight_kg=float(weight_kg),
        )

        raise ShipmentApplicationError(
            status_code=409,
            code="WAYBILL_CAINIAO_REQUEST_READY_BUT_DISABLED",
            message=(
                "cainiao request payload is ready: "
                "company_code/provider_code/customer_code/sender/receiver/weight "
                "have been mapped, but TOP request execution remains disabled "
                "until response mapping is confirmed"
            ),
        )

    def _map_order_channel(self, platform: str) -> str:
        key = str(platform or "").strip().upper()
        if key in self.ORDER_CHANNEL_MAP:
            return self.ORDER_CHANNEL_MAP[key]
        raise ShipmentApplicationError(
            status_code=409,
            code="WAYBILL_CAINIAO_ORDER_CHANNEL_UNSUPPORTED",
            message=f"unsupported cainiao order channel mapping for platform={key!r}",
        )

    @staticmethod
    def _build_package_info_id(req: WaybillRequest) -> str:
        package_no = req.extras.get("package_no")
        if package_no is None:
            package_no = 1
        return f"{req.platform}:{req.shop_id}:{req.ext_order_no}:{package_no}"

    def _build_waybill_cloud_print_apply_new_cols(
        self,
        *,
        req: WaybillRequest,
        company_code: str,
        provider_code: str,
        customer_code: str,
        sender_name: str,
        sender_mobile: str,
        sender_phone: str,
        sender_province: str,
        sender_city: str,
        sender_district: str,
        sender_address: str,
        receiver_name: str,
        receiver_phone: str,
        province: str,
        city: str,
        district: str,
        detail: str,
        weight_kg: float,
    ) -> dict[str, Any]:
        package_info_id = self._build_package_info_id(req)

        sender_contact_mobile = sender_mobile or ""
        sender_contact_phone = sender_phone or ""

        return {
            "company_code": company_code,
            "cp_code": provider_code,
            "trade_order_info_dtos": [
                {
                    "object_id": package_info_id,
                    "order_channels_type": self._map_order_channel(req.platform),
                    "trade_order_list": [
                        {
                            "trade_order_id": req.ext_order_no,
                        }
                    ],
                    "package_info": {
                        "id": package_info_id,
                        "items": [],
                        "weight": str(weight_kg),
                    },
                    "consignee": {
                        "name": receiver_name,
                        "mobile": receiver_phone,
                        "phone": "",
                        "address": {
                            "province": province,
                            "city": city,
                            "district": district,
                            "detail": detail,
                        },
                    },
                    "sender": {
                        "name": sender_name,
                        "mobile": sender_contact_mobile,
                        "phone": sender_contact_phone,
                        "address": {
                            "province": sender_province,
                            "city": sender_city,
                            "district": sender_district,
                            "detail": sender_address,
                        },
                    },
                    "wp_code": customer_code,
                    "product_type": "",
                    "logistics_services": [],
                    "extra_info": {},
                }
            ],
        }

    async def _call_waybill_ii_get(self, waybill_cloud_print_apply_new_cols: dict[str, Any]) -> dict[str, Any]:
        result = await self.client.post(
            method=self.TOP_METHOD,
            business_params={
                "waybill_cloud_print_apply_new_cols": json.dumps(
                    waybill_cloud_print_apply_new_cols,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            },
        )
        return result.response_json

    @staticmethod
    def _extract_waybill_result(response_json: dict[str, Any]) -> WaybillResult:
        """
        第一版真实响应映射目标：
        - 先识别 error_response
        - 成功响应优先解析：
          cainiao_waybill_ii_get_response.modules.waybill_cloud_print_info[0]
        - tracking_no <- waybill_code
        - print_data <- 二次解析后的 print_data JSON
        - template_url <- print_data 内 templateURL / template_url
        """
        root = response_json if isinstance(response_json, dict) else {}

        error_response = root.get("error_response")
        if isinstance(error_response, dict):
            return WaybillResult(
                ok=False,
                error_code=str(
                    error_response.get("sub_code")
                    or error_response.get("code")
                    or "WAYBILL_CAINIAO_TOP_ERROR"
                ),
                error_message=str(
                    error_response.get("sub_msg")
                    or error_response.get("msg")
                    or "cainiao top returned error_response"
                ),
                raw=root,
                source="CAINIAO_TOP",
            )

        success_root = root.get("cainiao_waybill_ii_get_response")
        if not isinstance(success_root, dict):
            return WaybillResult(
                ok=False,
                error_code="WAYBILL_CAINIAO_RESPONSE_EMPTY",
                error_message="cainiao top response root is missing",
                raw=root,
                source="CAINIAO_TOP",
            )

        modules = success_root.get("modules")
        if not isinstance(modules, dict):
            return WaybillResult(
                ok=False,
                error_code="WAYBILL_CAINIAO_MODULES_MISSING",
                error_message="cainiao top response modules is missing",
                raw=root,
                source="CAINIAO_TOP",
            )

        infos = modules.get("waybill_cloud_print_info")
        if not isinstance(infos, list) or not infos:
            return WaybillResult(
                ok=False,
                error_code="WAYBILL_CAINIAO_PRINT_INFO_MISSING",
                error_message="cainiao top response waybill_cloud_print_info is missing",
                raw=root,
                source="CAINIAO_TOP",
            )

        first = infos[0]
        if not isinstance(first, dict):
            return WaybillResult(
                ok=False,
                error_code="WAYBILL_CAINIAO_PRINT_INFO_INVALID",
                error_message="cainiao top response first waybill_cloud_print_info is invalid",
                raw=root,
                source="CAINIAO_TOP",
            )

        waybill_code = str(first.get("waybill_code") or "").strip()
        if not waybill_code:
            return WaybillResult(
                ok=False,
                error_code="WAYBILL_CAINIAO_WAYBILL_CODE_MISSING",
                error_message="cainiao top response waybill_code is missing",
                raw=root,
                source="CAINIAO_TOP",
            )

        print_data_raw = first.get("print_data")
        print_data_obj: dict[str, Any] | None = None

        if isinstance(print_data_raw, str):
            raw_text = print_data_raw.strip()
            if raw_text:
                try:
                    decoded = json.loads(raw_text)
                    if isinstance(decoded, dict):
                        print_data_obj = decoded
                except json.JSONDecodeError:
                    return WaybillResult(
                        ok=False,
                        error_code="WAYBILL_CAINIAO_PRINT_DATA_JSON_INVALID",
                        error_message="cainiao top response print_data is not valid json",
                        raw=root,
                        source="CAINIAO_TOP",
                    )
        elif isinstance(print_data_raw, dict):
            print_data_obj = print_data_raw

        if not isinstance(print_data_obj, dict):
            return WaybillResult(
                ok=False,
                error_code="WAYBILL_CAINIAO_PRINT_DATA_MISSING",
                error_message="cainiao top response print_data is missing",
                raw=root,
                source="CAINIAO_TOP",
            )

        template_url = str(
            print_data_obj.get("templateURL")
            or print_data_obj.get("template_url")
            or ""
        ).strip()

        signature = print_data_obj.get("signature")

        data_node = print_data_obj.get("data")
        if not isinstance(data_node, dict):
            data_node = {}

        normalized_print_data = {
            "signature": signature,
            "data": {
                "recipient": data_node.get("recipient") if isinstance(data_node.get("recipient"), dict) else {},
                "routingInfo": data_node.get("routingInfo") if isinstance(data_node.get("routingInfo"), dict) else {},
                "sender": data_node.get("sender") if isinstance(data_node.get("sender"), dict) else {},
                "shippingOption": (
                    data_node.get("shippingOption")
                    if isinstance(data_node.get("shippingOption"), dict)
                    else {}
                ),
                "cpCode": data_node.get("cpCode"),
                "waybillCode": str(data_node.get("waybillCode") or waybill_code).strip(),
            },
        }

        return WaybillResult(
            ok=True,
            tracking_no=waybill_code,
            print_data=normalized_print_data,
            template_url=template_url or None,
            raw=root,
            source="CAINIAO_TOP",
        )
