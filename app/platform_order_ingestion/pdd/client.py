# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
# app/platform_order_ingestion/pdd/client.py
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from .settings import PddOpenConfig
from .sign import build_pdd_sign


DEFAULT_RETRY_COUNT = 3
DEFAULT_INITIAL_DELAY_SECONDS = 1.0
DEFAULT_DATA_TYPE = "JSON"
DEFAULT_VERSION = "V1"


class PddOpenClientError(Exception):
    """PDD 开放平台客户端异常。"""


@dataclass(frozen=True)
class PddOpenClient:
    config: PddOpenConfig
    timeout_seconds: float = 15.0
    retry_count: int = DEFAULT_RETRY_COUNT
    initial_delay_seconds: float = DEFAULT_INITIAL_DELAY_SECONDS

    async def post(
        self,
        *,
        api_type: str,
        business_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        api_type_text = str(api_type or "").strip()
        if not api_type_text:
            raise PddOpenClientError("api_type is required")

        payload: Dict[str, Any] = {
            "type": api_type_text,
            "client_id": self.config.client_id,
            "timestamp": int(time.time()),
            "data_type": DEFAULT_DATA_TYPE,
            "version": DEFAULT_VERSION,
        }
        if business_params:
            payload.update(business_params)

        payload["sign"] = build_pdd_sign(
            params=payload,
            client_secret=self.config.client_secret,
        )

        headers = {"content-type": "application/json"}

        last_error: Optional[Exception] = None
        delay = self.initial_delay_seconds

        for attempt in range(1, self.retry_count + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        self.config.api_base_url,
                        headers=headers,
                        json=payload,
                    )
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= self.retry_count:
                    raise PddOpenClientError(f"pdd open http request error: {exc}") from exc
                await asyncio.sleep(delay)
                delay *= 2
                continue

            if response.status_code >= 500:
                last_error = PddOpenClientError(
                    f"pdd open http status error: {response.status_code}"
                )
                if attempt >= self.retry_count:
                    raise last_error
                await asyncio.sleep(delay)
                delay *= 2
                continue

            if response.status_code >= 400:
                raise PddOpenClientError(
                    f"pdd open http status error: {response.status_code}"
                )

            try:
                data = response.json()
            except ValueError as exc:
                raise PddOpenClientError("pdd open returned non-json response") from exc

            if not isinstance(data, dict):
                raise PddOpenClientError("pdd open returned non-object json")

            error_response = data.get("error_response")
            if isinstance(error_response, dict):
                if self._is_retryable_error_response(error_response) and attempt < self.retry_count:
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                raise PddOpenClientError(
                    f"pdd open error_response returned: {error_response}"
                )

            return data

        raise PddOpenClientError(f"pdd open request failed: {last_error}")

    def _is_retryable_error_response(self, error_response: Dict[str, Any]) -> bool:
        text = " ".join(
            str(error_response.get(key) or "")
            for key in ("sub_msg", "msg", "error_msg", "sub_code", "error_code")
        ).lower()

        retry_markers = (
            "frequency",
            "limit",
            "too many",
            "timeout",
            "temporarily unavailable",
            "system busy",
            "busy",
        )
        return any(marker in text for marker in retry_markers)
