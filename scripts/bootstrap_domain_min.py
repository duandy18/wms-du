#!/usr/bin/env python3
from __future__ import annotations
import argparse, asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from app.db.base import init_models
init_models()

from app.services.store_service import StoreService

SQL_ENSURE_WAREHOUSE = """
INSERT INTO warehouses(id, name) VALUES (1, 'WH-1')
ON CONFLICT (id) DO NOTHING;
"""

SQL_ENSURE_LOCATION = """
INSERT INTO locations(id, name, warehouse_id) VALUES (1, 'L1', 1)
ON CONFLICT (id) DO NOTHING;
"""

# 修正点：items 需要 NOT NULL 的 sku，这里一并写入
SQL_ENSURE_ITEM = """
INSERT INTO items(id, sku, name, unit)
VALUES (:id, :sku, :name, 'bag')
ON CONFLICT (id) DO NOTHING;
"""

SQL_ENSURE_STOCK_ROW = """
INSERT INTO stocks(item_id, location_id, qty)
VALUES (:item_id, :loc, 0)
ON CONFLICT (item_id, location_id) DO NOTHING;
"""

async def _run(store_name: str, item_ids: list[int], db_url: str):
    engine = create_async_engine(db_url, future=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as s:
        # 1) 维度 & 基础行
        await s.execute(text(SQL_ENSURE_WAREHOUSE))
        await s.execute(text(SQL_ENSURE_LOCATION))
        for iid in item_ids:
            await s.execute(
                text(SQL_ENSURE_ITEM),
                {"id": iid, "sku": f"SKU-{iid}", "name": f"ITEM-{iid}"},
            )
            await s.execute(text(SQL_ENSURE_STOCK_ROW), {"item_id": iid, "loc": 1})
        await s.commit()

        # 2) 店与映射
        sid = await StoreService.ensure_store(s, name=store_name, platform="pdd", active=True)
        for iid in item_ids:
            await StoreService.upsert_store_item(s, store_id=sid, item_id=iid, pdd_sku_id=str(iid))

        # 3) 影子刷新（不落表）
        ref = await StoreService.refresh_channel_inventory_for_store(s, store_id=sid, dry_run=True)
        print({"store_id": sid, "items": ref["items"]})

    await engine.dispose()

def main():
    ap = argparse.ArgumentParser(description="Bootstrap minimal domain: wh/loc/items/stocks/store/bind + shadow refresh")
    ap.add_argument("--store", default="主店A")
    ap.add_argument("--items", default="777,778")
    ap.add_argument("--db", default="postgresql+asyncpg://wms:wms@127.0.0.1:5433/wms")
    a = ap.parse_args()
    ids = [int(x) for x in a.items.split(",") if x.strip()]
    asyncio.run(_run(a.store, ids, a.db))

if __name__ == "__main__":
    main()
