# app/limits.py
from __future__ import annotations

import time
from typing import Dict, Optional, Tuple

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession


class TokenBucket:
    """简单令牌桶：capacity=fill_rate（QPS），按秒补充"""

    def __init__(self, capacity: int, fill_rate: float):
        self.capacity = max(1, int(capacity))
        self.fill_rate = float(fill_rate)
        self.tokens = float(self.capacity)
        self.ts = time.time()

    def allow(self, n: int = 1) -> bool:
        now = time.time()
        self.tokens = min(self.capacity, self.tokens + (now - self.ts) * self.fill_rate)
        self.ts = now
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False


# 进程内桶缓存：每个 (platform, shop_id) 一个
_BUCKETS: Dict[Tuple[str, str], TokenBucket] = {}


async def ensure_bucket(session: AsyncSession, platform: str, shop_id: str) -> TokenBucket:
    """
    按 (platform, shop_id) 返回一个令牌桶。
    QPS 由 platform_shops.rate_limit_qps 决定，若表/行不存在则默认 5。
    """
    key = (platform, shop_id)
    if key in _BUCKETS:
        return _BUCKETS[key]

    q = sa.text(
        """
        SELECT COALESCE(rate_limit_qps,5)
        FROM platform_shops
        WHERE platform=:p AND shop_id=:s
        LIMIT 1
    """
    )
    try:
        qps: Optional[int] = (
            await session.execute(q, {"p": platform, "s": shop_id})
        ).scalar_one_or_none()
    except Exception:
        qps = None
    qps = qps if (qps and qps > 0) else 5
    bucket = TokenBucket(capacity=qps, fill_rate=qps)
    _BUCKETS[key] = bucket
    return bucket
