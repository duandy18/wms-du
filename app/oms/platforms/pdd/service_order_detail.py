# app/oms/platforms/pdd/service_order_detail.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from .access_repository import get_credential_by_store_platform
from .service_decrypt import PddDecryptService, PddDecryptServiceError
from .client import PddOpenClient, PddOpenClientError
from .contracts import PddOrderDetail, PddOrderDetailItem
from .repository import require_enabled_pdd_app_config
from .settings import build_pdd_open_config_from_model


PDD_PLATFORM = "pdd"
PDD_ORDER_INFORMATION_API_TYPE = "pdd.order.information.get"


class PddOrderDetailServiceError(Exception):
    """OMS 拼多多订单详情服务异常。"""


class PddOrderDetailService:
    """
    PDD 订单详情补全第一版。

    当前阶段职责：
    - 使用 order_sn 调用 pdd.order.information.get
    - 提取省市区、脱敏收件信息、买家留言、商家备注、商品明细
    - 使用解密服务解密脱敏字段
    - 不做解密后 OMS ingest
    """

    async def fetch_order_detail(
        self,
        *,
        session: AsyncSession,
        store_id: int,
        order_sn: str,
    ) -> PddOrderDetail:
        store_id_int = int(store_id)
        order_sn_text = str(order_sn or "").strip()

        if store_id_int <= 0:
            raise PddOrderDetailServiceError("store_id must be positive")
        if not order_sn_text:
            raise PddOrderDetailServiceError("order_sn is required")

        app_config = await require_enabled_pdd_app_config(session)
        config = build_pdd_open_config_from_model(app_config)

        credential = await get_credential_by_store_platform(
            session,
            store_id=store_id_int,
            platform=PDD_PLATFORM,
        )
        if credential is None:
            raise PddOrderDetailServiceError("pdd credential not found")

        client = PddOpenClient(config=config)
        try:
            payload = await client.post(
                api_type=PDD_ORDER_INFORMATION_API_TYPE,
                business_params={
                    "order_sn": order_sn_text,
                    "access_token": credential.access_token,
                },
            )
        except PddOpenClientError as exc:
            raise PddOrderDetailServiceError(
                f"pdd order information request failed: {exc}"
            ) from exc

        order_info = self._parse_order_info(payload)

        decrypt_service = PddDecryptService(config=config)
        if order_info.get("data_tag"):
            try:
                decrypted = await decrypt_service.decrypt_fields(
                    store_id=store_id_int,
                    data_tags=[order_info["data_tag"]],
                    fields=["receiver_name", "receiver_phone", "receiver_address"],
                )
                if isinstance(decrypted, dict):
                    order_info["receiver_name"] = decrypted.get(
                        "receiver_name",
                        order_info.get("receiver_name"),
                    )
                    order_info["receiver_phone"] = decrypted.get(
                        "receiver_phone",
                        order_info.get("receiver_phone"),
                    )
                    order_info["receiver_address"] = decrypted.get(
                        "receiver_address",
                        order_info.get("receiver_address") or order_info.get("address"),
                    )
            except PddDecryptServiceError as exc:
                raise PddOrderDetailServiceError(f"Failed to decrypt: {exc}") from exc

        return self._parse_detail(order_info)

    def _parse_order_info(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        response_obj = payload.get("order_info_get_response")
        if not isinstance(response_obj, dict):
            raise PddOrderDetailServiceError(
                f"pdd order detail missing order_info_get_response: {payload}"
            )

        order_info = response_obj.get("order_info")
        if not isinstance(order_info, dict):
            raise PddOrderDetailServiceError(
                f"pdd order detail missing order_info: {payload}"
            )

        order_sn = self._first_non_empty_str(order_info, "order_sn", "order_no", "order_id")
        if not order_sn:
            raise PddOrderDetailServiceError(f"pdd order detail missing order_sn: {payload}")

        return order_info

    def _parse_detail(self, order_info: Dict[str, Any]) -> PddOrderDetail:
        items: List[PddOrderDetailItem] = []
        items_raw = order_info.get("item_list")
        if isinstance(items_raw, list):
            for item in items_raw:
                if not isinstance(item, dict):
                    continue

                goods_count = 0
                try:
                    goods_count = int(item.get("goods_count") or 0)
                except (TypeError, ValueError):
                    goods_count = 0

                goods_price: Optional[int] = None
                raw_price = item.get("goods_price")
                if raw_price is not None:
                    try:
                        goods_price = int(raw_price)
                    except (TypeError, ValueError):
                        goods_price = None

                items.append(
                    PddOrderDetailItem(
                        goods_id=self._first_non_empty_str(item, "goods_id"),
                        goods_name=self._first_non_empty_str(item, "goods_name"),
                        sku_id=self._first_non_empty_str(item, "sku_id"),
                        outer_id=self._first_non_empty_str(item, "outer_id"),
                        goods_count=goods_count,
                        goods_price=goods_price,
                        raw_item=item,
                    )
                )

        receiver_address_masked = self._first_non_empty_str(
            order_info,
            "receiver_address",
            "address",
        )

        return PddOrderDetail(
            order_sn=self._first_non_empty_str(order_info, "order_sn", "order_no", "order_id") or "",
            province=self._first_non_empty_str(order_info, "province"),
            city=self._first_non_empty_str(order_info, "city"),
            town=self._first_non_empty_str(order_info, "town"),
            receiver_name_masked=self._first_non_empty_str(order_info, "receiver_name"),
            receiver_phone_masked=self._first_non_empty_str(order_info, "receiver_phone"),
            receiver_address_masked=receiver_address_masked,
            buyer_memo=self._first_non_empty_str(order_info, "buyer_memo"),
            remark=self._first_non_empty_str(order_info, "remark"),
            items=items,
            raw_payload=order_info,
        )

    def _first_non_empty_str(self, data: Dict[str, Any], *keys: str) -> Optional[str]:
        for key in keys:
            value = str(data.get(key) or "").strip()
            if value:
                return value
        return None
