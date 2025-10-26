#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# ★ 集中导入 & 映射校验
from app.db.base import init_models
init_models()

from app.services.store_service import StoreService


async def _run(store_id: int, db_url: str, apply: bool):
    engine = create_async_engine(db_url, future=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with async_session() as s:
            res = await StoreService.refresh_channel_inventory_for_store(
                s, store_id=store_id, dry_run=not apply
            )
            print(res)
    finally:
        await engine.dispose()


def main():
    p = argparse.ArgumentParser(description="Shadow refresh for a store")
    p.add_argument("--store-id", type=int, required=True)
    p.add_argument("--db", default="postgresql+asyncpg://wms:wms@127.0.0.1:5433/wms")
    p.add_argument("--apply", action="store_true", help="写回 visible_qty（默认只影子计算）")
    args = p.parse_args()
    asyncio.run(_run(args.store_id, args.db, args.apply))


if __name__ == "__main__":
    main()
