# app/oms/platforms/taobao/top_client.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Mapping

import httpx

from .contracts import TaobaoTopRequest, TaobaoTopResponse
from .errors import TaobaoTopHttpError, TaobaoTopProtocolError
from .settings import TaobaoTopConfig
from .top_sign import build_top_sign


class TaobaoTopClient:
    """
    TOP 协议发送器。

    职责：
    - 组装 TOP 公共参数
    - 注入 session
    - 计算 sign
    - POST 到 TOP 网关
    - 识别 error_response
    - 返回原始 JSON 与成功 body

    不负责：
    - OMS 业务判断
    - 持久化
    - 前端 contract 组装
    - OAuth / code->token / session 来源管理
    """

    def __init__(
        self,
        config: TaobaoTopConfig,
        *,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.config = config
        self.timeout_seconds = timeout_seconds

    async def call(self, request: TaobaoTopRequest) -> TaobaoTopResponse:
        payload = self._build_payload(request)

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(self.config.api_base_url, data=payload)

        if response.status_code >= 400:
            raise TaobaoTopHttpError(
                f"taobao top http error: {response.status_code}",
                status_code=response.status_code,
                payload=response.text,
            )

        try:
            raw = response.json()
        except Exception as exc:
            raise TaobaoTopHttpError(
                "taobao top returned non-json response",
                status_code=response.status_code,
                payload=response.text,
            ) from exc

        if "error_response" in raw:
            error_payload = raw["error_response"]
            raise TaobaoTopProtocolError(
                "taobao top error_response returned",
                code=str(error_payload.get("code") or ""),
                payload=error_payload,
            )

        body = self._extract_success_body(raw)
        return TaobaoTopResponse(raw=raw, body=body)

    def _build_payload(self, request: TaobaoTopRequest) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "method": request.method,
            "app_key": self.config.app_key,
            "format": request.format,
            "v": request.version,
            "sign_method": request.sign_method or self.config.sign_method,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "simplify": "true" if request.simplify else "false",
        }

        if request.partner_id:
            payload["partner_id"] = request.partner_id
        if request.session:
            payload["session"] = request.session

        for key, value in request.biz_params.items():
            payload[key] = value

        payload["sign"] = build_top_sign(
            payload,
            self.config.app_secret,
            sign_method=str(payload["sign_method"]),
        )
        return payload

    @staticmethod
    def _extract_success_body(raw: Mapping[str, Any]) -> Dict[str, Any]:
        if not raw:
            return {}

        if len(raw) == 1:
            only_value = next(iter(raw.values()))
            if isinstance(only_value, dict):
                return dict(only_value)

        for key, value in raw.items():
            if key.endswith("_response") and isinstance(value, dict):
                return dict(value)

        return dict(raw)
