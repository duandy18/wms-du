from __future__ import annotations

import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db.session import async_session_maker
from app.services.snapshot_service import SnapshotService

_scheduler: AsyncIOScheduler | None = None


async def _job_run_yesterday():
    async with async_session_maker() as session:  # type: AsyncSession
        await SnapshotService.run_yesterday(session, sync_unbatched_from_stocks=True)


def init_scheduler():
    global _scheduler
    if os.getenv("ENABLE_SNAPSHOT_SCHEDULER") != "1":
        return
    _scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
    _scheduler.add_job(_job_run_yesterday, "cron", hour=0, minute=5)
    _scheduler.start()
