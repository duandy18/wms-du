#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import csv
from pathlib import Path
from typing import Dict, List

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# ★ 集中导入 & 映射校验
from app.db.base import init_models

init_models()

from app.adapters.registry import get_adapter

# 开关与适配器注册表
from app.config.flags import ENABLE_PDD_PULL
from app.services.store_service import StoreService


async def _pull_platform_qty(
    session: AsyncSession, store_id: int, item_ids: List[int], verbose: bool
) -> Dict[int, int]:
    """
    若 ENABLE_PDD_PULL=true 则通过适配器拉平台库存；否则返回全 0（影子期）。
    v1.1：单平台 PDD；后续可按 store.platform 动态路由。
    """
    if not ENABLE_PDD_PULL:
        return {iid: 0 for iid in item_ids}

    adapter = get_adapter("pdd")  # 现阶段默认单平台
    if verbose:
        try:
            preview = await adapter.build_fetch_preview(
                session, store_id=store_id, item_ids=item_ids
            )
            # 打印简洁预览（不泄露秘钥）
            print(
                "[PDD fetch preview]",
                {
                    "store_id": preview.get("store_id"),
                    "creds_ready": preview.get("creds_ready"),
                    "ext_sku_ids": preview.get("ext_sku_ids"),
                    "signature": preview.get("signature"),
                },
            )
        except Exception as e:
            print("[PDD fetch preview] error:", e)

    return await adapter.fetch_inventory(store_id=store_id, item_ids=item_ids)


async def _run(store_id: int, out_csv: Path, db_url: str, verbose: bool):
    engine = create_async_engine(db_url, future=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as s:
            # 影子计算系统可见量（A 策略）
            ref = await StoreService.refresh_channel_inventory_for_store(
                s, store_id=store_id, dry_run=True
            )
            items = ref["items"]
            item_ids = [int(x["item_id"]) for x in items]
            system_visible = {int(x["item_id"]): int(x["visible"]) for x in items}

            # 平台侧库存：影子 0 / 适配器拉数
            platform_qty = await _pull_platform_qty(s, store_id, item_ids, verbose)

            # 输出 CSV
            out_csv.parent.mkdir(parents=True, exist_ok=True)
            with out_csv.open("w", newline="") as f:
                w = csv.writer(f)
                w.writerow(
                    ["store_id", "item_id", "platform_qty", "system_visible_qty", "delta", "advice"]
                )
                for iid in item_ids:
                    plat = int(platform_qty.get(iid, 0))
                    sysv = int(system_visible.get(iid, 0))
                    delta = plat - sysv
                    advice = "PUSH" if delta != 0 else ""
                    w.writerow([store_id, iid, plat, sysv, delta, advice])
            if verbose:
                print("[reconcile]", out_csv, "written")
    finally:
        await engine.dispose()


def main():
    p = argparse.ArgumentParser(description="PDD daily reconcile (shadow or adapter-backed)")
    p.add_argument("--store-id", type=int, required=True)
    p.add_argument("--db", default="postgresql+asyncpg://wms:wms@127.0.0.1:5433/wms")
    p.add_argument("--out", default="./var/reconcile/pdd_daily.csv")
    p.add_argument("--verbose", action="store_true", help="打印适配器请求预览与输出路径")
    args = p.parse_args()
    asyncio.run(_run(args.store_id, Path(args.out), args.db, args.verbose))


if __name__ == "__main__":
    main()
