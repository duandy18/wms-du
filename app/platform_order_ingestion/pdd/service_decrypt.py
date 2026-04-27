# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
# app/platform_order_ingestion/pdd/service_decrypt.py
from __future__ import annotations

import asyncio
from typing import List

from app.platform_order_ingestion.pdd.client import PddOpenClient, PddOpenClientError


DECRYPT_BATCH_SIZE = 50
RETRY_COUNT = 3
INITIAL_DELAY_SECONDS = 1


class PddDecryptServiceError(Exception):
    """PDD 解密服务异常。"""


class PddDecryptService:
    """
    PDD 解密服务，负责批量调用 `pdd.open.decrypt.mask.batch`。
    """

    def __init__(self, config):
        self.client = PddOpenClient(config=config)
        self.retry_count = RETRY_COUNT
        self.initial_delay_seconds = INITIAL_DELAY_SECONDS

    async def decrypt_fields(
        self, *, store_id: int, data_tags: List[str], fields: List[str]
    ) -> dict:
        """
        批量解密指定字段。
        """
        payload = {
            "data_tags": data_tags,
            "fields": fields,
        }

        last_error = None
        delay = self.initial_delay_seconds

        for attempt in range(1, self.retry_count + 1):
            try:
                response = await self.client.post(
                    api_type="pdd.open.decrypt.mask.batch", business_params=payload
                )
                return response
            except PddOpenClientError as exc:
                last_error = exc
                if attempt >= self.retry_count:
                    raise PddDecryptServiceError(f"Decrypt failed: {exc}") from exc
                await asyncio.sleep(delay)
                delay *= 2

        raise PddDecryptServiceError(f"Decrypt failed: {last_error}")
