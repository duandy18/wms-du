# app/jobs/reserve_ttl.py
"""
Soft Reserve TTL Job（统一入口）

目标：
  - 只处理 Soft Reserve / reservations(status='open', expire_at < now)
  - 不再触碰 legacy 的 release_reservation / stock_ledger
  - 并发安全 & 幂等由 SoftReserveService 实现

用法：
  - 本地/生产均可使用：
        python -m app.jobs.reserve_ttl
  - 也可以由 scheduler 定期调用 main()。
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.services.soft_reserve_ttl import sweep_soft_reserve_ttl

UTC = timezone.utc


def _get_batch_size() -> int:
    raw = os.getenv("SOFT_RESERVE_TTL_BATCH_SIZE") or "100"
    try:
        value = int(raw)
        return value if value > 0 else 100
    except Exception:
        return 100


async def main() -> None:
    """
    独立运行入口（例如：python -m app.jobs.reserve_ttl）。

    行为：
      - 连接与应用相同的 DATABASE_URL；
      - 调用 sweep_soft_reserve_ttl 扫描并回收过期 reservations；
      - 最后提交事务并打印处理数量。
    """
    settings = get_settings()
    url = settings.DATABASE_URL

    engine = create_async_engine(url, poolclass=NullPool, future=True)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    batch_size = _get_batch_size()
    now = datetime.now(UTC)

    try:
        async with maker() as session:
            processed = await sweep_soft_reserve_ttl(
                session,
                now=now,
                batch_size=batch_size,
                reason="expired",
            )
            await session.commit()
            print(f"[SoftTTL] processed {processed} expired reservations (batch_size={batch_size})")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
