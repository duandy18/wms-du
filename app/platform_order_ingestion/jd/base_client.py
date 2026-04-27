# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
# app/platform_order_ingestion/jd/base_client.py
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Mapping, Optional

import httpx

from .errors import JdJosHttpError, JdJosProtocolError
from .settings import JdJosConfig
from .sign import build_jd_sign


class BaseJdClient:
    """
    JOS 协议发送器。

    第一阶段职责：
    - 组装 JD/JOS 系统参数
    - 将业务参数打包到 360buy_param_json
    - 计算 sign
    - POST 到 JOS 网关
    - 解析原始 JSON
    - 识别协议层错误

    不负责：
    - 商家授权流程
    - token 持久化
    - OMS 业务判断
    - 事实表入库
    - 前端 contract 组装
    """

    def __init__(
        self,
        config: JdJosConfig,
        *,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.config = config
        self.timeout_seconds = timeout_seconds

    def pack_biz_params(self, payload: Mapping[str, Any]) -> str:
        """
        将业务参数装箱成 360buy_param_json。

        当前策略：
        - 使用紧凑 JSON
        - 保留 UTF-8 原始字符
        - 不展开内部字段参与外部排序
        """
        return json.dumps(
            dict(payload),
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def build_system_params(
        self,
        *,
        method: str,
        biz_json: str,
        access_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "method": method,
            "app_key": self.config.client_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "v": self.config.version,
            "360buy_param_json": biz_json,
        }
        if access_token:
            payload["access_token"] = access_token
        return payload

    def build_sign(self, params: Mapping[str, Any]) -> str:
        return build_jd_sign(params, self.config.client_secret)

    async def call(
        self,
        *,
        method: str,
        biz_params: Mapping[str, Any],
        access_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        biz_json = self.pack_biz_params(biz_params)
        payload = self.build_system_params(
            method=method,
            biz_json=biz_json,
            access_token=access_token,
        )
        payload["sign"] = self.build_sign(payload)

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(self.config.gateway_url, data=payload)

        if response.status_code >= 400:
            raise JdJosHttpError(
                f"jd jos http error: {response.status_code}",
                status_code=response.status_code,
                payload=response.text,
            )

        try:
            raw = response.json()
        except Exception as exc:
            raise JdJosHttpError(
                "jd jos returned non-json response",
                status_code=response.status_code,
                payload=response.text,
            ) from exc

        return self._parse_response(raw)

    def _parse_response(self, raw: Mapping[str, Any]) -> Dict[str, Any]:
        """
        第一阶段只做最小 envelope 识别。

        现阶段约定：
        - 返回原始 dict
        - 若明显出现错误结构，则抛协议异常
        """
        if not isinstance(raw, Mapping):
            raise JdJosProtocolError(
                "jd jos response is not a mapping",
                payload=raw,
            )

        error_code, error_message = self._classify_error(raw)
        if error_code is not None:
            raise JdJosProtocolError(
                error_message or "jd jos protocol error",
                code=str(error_code),
                payload=dict(raw),
            )

        return dict(raw)

    @staticmethod
    def _classify_error(raw: Mapping[str, Any]) -> tuple[Optional[str], Optional[str]]:
        """
        JD 返回体目前先做保守识别。

        兼容几类常见形态：
        - {"code": "...", "msg": "..."}
        - {"error_response": {...}}
        - 其他未识别结构先视为成功原样返回

        后续真实联调后，再根据真实 envelope 收紧。
        """
        if "error_response" in raw:
            error_payload = raw.get("error_response")
            if isinstance(error_payload, Mapping):
                code = error_payload.get("code")
                msg = error_payload.get("msg") or error_payload.get("message")
                return (
                    str(code) if code is not None else None,
                    str(msg) if msg is not None else "jd jos error_response returned",
                )
            return (None, "jd jos error_response returned")

        code = raw.get("code")
        if code is not None:
            code_str = str(code).strip()
            if code_str and code_str not in {"0", "200"}:
                msg = raw.get("msg") or raw.get("message") or raw.get("zh_desc")
                return (code_str, str(msg) if msg is not None else "jd jos error returned")

        return (None, None)
