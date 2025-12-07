#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import init_models

init_models()
from app.services.channel_inventory_service import ChannelInventoryService
from app.services.store_service import StoreService


async def run(store_id: int, item_id: int, qty: int, db: str):
    eng = create_async_engine(db, future=True)
    ses = sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    async with ses() as s:
        new_reserved = await ChannelInventoryService.adjust_reserved(
            s, store_id=store_id, item_id=item_id, delta=qty
        )
        await StoreService.refresh_channel_inventory_for_store(
            s, store_id=store_id, item_ids=[item_id], dry_run=False
        )
        print({"store_id": store_id, "item_id": item_id, "reserved_qty": new_reserved})
    await eng.dispose()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--store-id", type=int, required=True)
    ap.add_argument("--item-id", type=int, required=True)
    ap.add_argument("--qty", type=int, required=True)
    ap.add_argument("--db", default="postgresql+asyncpg://wms:wms@127.0.0.1:5433/wms")
    a = ap.parse_args()
    asyncio.run(run(a.store_id, a.item_id, a.qty, a.db))


if __name__ == "__main__":
    main()
