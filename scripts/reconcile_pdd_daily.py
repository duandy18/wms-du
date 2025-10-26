#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import csv
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# ★ 集中导入 & 映射校验
from app.db.base import init_models
init_models()

from app.services.store_service import StoreService


async def _pull_pdd_platform_qty(store_id: int, item_ids: list[int]) -> dict[int, int]:
    # 影子期：平台库存拉取留空（返回 0），便于观察 delta
    return {iid: 0 for iid in item_ids}


async def _run(store_id: int, out_csv: Path, db_url: str):
    engine = create_async_engine(db_url, future=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as s:
            # 影子计算系统可见量
            ref = await StoreService.refresh_channel_inventory_for_store(s, store_id=store_id, dry_run=True)
            items = ref["items"]
            item_ids = [x["item_id"] for x in items]
            system_visible = {x["item_id"]: int(x["visible"]) for x in items}

            # 平台侧库存（占位符）
            platform_qty = await _pull_pdd_platform_qty(store_id, item_ids)

            # 输出 CSV
            out_csv.parent.mkdir(parents=True, exist_ok=True)
            with out_csv.open("w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["store_id", "item_id", "platform_qty", "system_visible_qty", "delta", "advice"])
                for iid in item_ids:
                    plat = int(platform_qty.get(iid, 0))
                    sysv = int(system_visible.get(iid, 0))
                    delta = plat - sysv
                    advice = "PUSH" if delta != 0 else ""
                    w.writerow([store_id, iid, plat, sysv, delta, advice])
    finally:
        await engine.dispose()


def main():
    p = argparse.ArgumentParser(description="PDD daily reconcile (shadow)")
    p.add_argument("--store-id", type=int, required=True)
    p.add_argument("--db", default="postgresql+asyncpg://wms:wms@127.0.0.1:5433/wms")
    p.add_argument("--out", default="./var/reconcile/pdd_daily.csv")
    args = p.parse_args()
    asyncio.run(_run(args.store_id, Path(args.out), args.db))


if __name__ == "__main__":
    main()
