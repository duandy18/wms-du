#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# ★ 确保脚本也完成模型集中导入与映射校验
from app.db.base import init_models
init_models()

from app.services.store_service import StoreService


async def _run(store_name: str, item_ids: list[int], db_url: str):
    engine = create_async_engine(db_url, future=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with async_session() as s:
            sid = await StoreService.ensure_store(s, name=store_name, platform="pdd", active=True)
            for iid in item_ids:
                await StoreService.upsert_store_item(s, store_id=sid, item_id=iid, pdd_sku_id=str(iid))
            ref = await StoreService.refresh_channel_inventory_for_store(s, store_id=sid, dry_run=True)
            print({"store_id": sid, "items": ref["items"]})
    finally:
        await engine.dispose()


def main():
    p = argparse.ArgumentParser(description="Bootstrap single store (PDD) and bind items")
    p.add_argument("--store", required=True, help="store name, e.g. 主店A or shop_id")
    p.add_argument("--items", required=True, help="comma-separated internal item_ids, e.g. 777,778")
    p.add_argument("--db", default="postgresql+asyncpg://wms:wms@127.0.0.1:5433/wms")
    a = p.parse_args()
    ids = [int(x) for x in a.items.split(",") if x.strip()]
    asyncio.run(_run(a.store, ids, a.db))


if __name__ == "__main__":
    main()
