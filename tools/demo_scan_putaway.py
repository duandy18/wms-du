import asyncio
import os
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# 读取环境变量（默认指向你当前库）
DB_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://wms:wms@127.0.0.1:5433/wms")
os.environ.setdefault("SCAN_REAL_PUTAWAY", "1")  # 默认开启真动作

engine = create_async_engine(DB_URL, echo=False, future=True)
Session = async_sessionmaker(engine, expire_on_commit=False)


async def main():
    from app.services.scan_gateway import ingest

    async with Session() as session:
        # 1) 兜底基线：库位/物料
        await session.execute(
            text(
                """
            INSERT INTO locations(id, name, warehouse_id)
            VALUES (1,'LOC-1',1) ON CONFLICT (id) DO NOTHING
        """
            )
        )
        try:
            await session.execute(
                text(
                    """
                INSERT INTO items(id, name, sku)
                VALUES (1,'DEMO-ITEM','SKU-1') ON CONFLICT (id) DO NOTHING
            """
                )
            )
        except Exception:
            await session.execute(
                text("INSERT INTO items(id) VALUES (1) ON CONFLICT (id) DO NOTHING")
            )

        # 2) 构造一条扫描（显式指定 item/location，避免解析差异）
        ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        scan = {
            "device_id": "RF01",
            "operator": "demo",
            "barcode": "LOC:1",  # 仅用于生成 dedup
            "mode": "putaway",
            "qty": 1,
            "item_id": 1,
            "location_id": 1,
            "ts": ts,
            "ctx": {"warehouse_id": 1},
        }

        # 3) 触发真动作上架并提交
        result = await ingest(scan, session)
        await session.commit()

        print("INGEST RESULT:", result)

        # 4) 打印最近几条日志（便于肉眼取证）
        rows = (
            await session.execute(
                text(
                    """
            SELECT id, source, message, created_at
              FROM event_log
             WHERE source IN ('scan_ingest','scan_route','scan_putaway_path','scan_putaway_commit','scan_route_probe_error')
          ORDER BY id DESC LIMIT 10
        """
                )
            )
        ).fetchall()
        print("EVENT_LOG TOP10:")
        for r in rows:
            print(dict(r._mapping))


if __name__ == "__main__":
    asyncio.run(main())
