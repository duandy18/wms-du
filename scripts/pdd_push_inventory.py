#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.services.store_service import StoreService


async def _run(store_id: int, db_url: str, apply: bool):
    engine = create_async_engine(db_url, future=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with async_session() as s:
            # 影子计算（不落表），用可见量 visible 作为推送载荷
            ref = await StoreService.refresh_channel_inventory_for_store(
                s, store_id=store_id, dry_run=True
            )
            payload = [{"item_id": x["item_id"], "qty": x["visible"]} for x in ref["items"]]
            print(json.dumps({"store_id": store_id, "items": payload}, ensure_ascii=False, indent=2))
            if apply:
                # 这里未来接 PDD 正式推送（签名、频控、失败落表重试）
                print("TODO: push to PDD -> not implemented (shadow mode).")
    finally:
        await engine.dispose()


def main():
    p = argparse.ArgumentParser(description="Preview or push PDD inventory payload")
    p.add_argument("--store-id", type=int, required=True)
    p.add_argument("--db", default="postgresql+asyncpg://wms:wms@127.0.0.1:5433/wms")
    p.add_argument("--apply", action="store_true", help="默认仅预览，加 --apply 才执行真实推送（当前仍未实现）")
    args = p.parse_args()
    asyncio.run(_run(args.store_id, args.db, args.apply))


if __name__ == "__main__":
    main()
