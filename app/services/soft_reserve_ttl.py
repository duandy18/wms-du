from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from .soft_reserve_service import SoftReserveService


async def sweep_soft_reserve_ttl(
    session: AsyncSession,
    *,
    now: Optional[datetime] = None,
    batch_size: int = 100,
    reason: str = "expired",
) -> int:
    """
    扫描并回收 soft reserve 的 TTL 过期单。

    语义：
      - 仅处理：
          reservations.status = 'open'
          AND expire_at IS NOT NULL
          AND expire_at < :now
      - 对每个候选 id 调用 SoftReserveService.release_expired_by_id：
          * 首次：status='EXPIRED'
          * 重复 / 已被其它路径处理：status='NOOP'
      - 不修改 stocks / stock_ledger，只改 reservations.status。

    参数：
      session    : AsyncSession，由调用方提供（测试环境 / 线上都统一）
      now        : 基准时间，便于测试中用固定时间；None 时取当前 UTC
      batch_size : 单次最多处理多少个 id
      reason     : 写入 reservations.status 的值，默认 'expired'

    返回：
      int : 本次调用中真正从 open -> expired 的 reservation 数量。
    """
    if now is None:
        now = datetime.now(timezone.utc)

    svc = SoftReserveService()
    total_expired = 0

    while True:
        # 1) 扫一批候选 id（不加锁，只读）
        ids = await svc.find_expired(session, now=now, limit=batch_size)
        if not ids:
            break

        # 2) 逐个在“事务 + advisory lock”保护下执行 TTL 释放
        for rid in ids:
            result = await svc.release_expired_by_id(
                session,
                reservation_id=rid,
                reason=reason,
            )
            if result.get("status") == "EXPIRED":
                total_expired += 1

        # 如果本批数量已经小于 batch_size，可以提前结束（说明尾部了）
        if len(ids) < batch_size:
            break

    return total_expired
