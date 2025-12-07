# 保存成 scratch_probe.py 并用 PYTHONPATH=. python scratch_probe.py 运行
import asyncio
import httpx
from app.main import app


async def main():
    payload = {
        "mode": "pick",
        "tokens": {"barcode": "TASK:42 LOC:1 ITEM:3001 QTY:2"},
        "ctx": {"device_id": "RF01", "operator": "qa"},
        "probe": True,
    }
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/scan", json=payload)
        print("resp.status:", r.status_code)
        print("resp.json:", r.json())


asyncio.run(main())
