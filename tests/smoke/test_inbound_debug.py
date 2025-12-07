from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test__scan_receive_debug_once():
    """
    第三版调试：尝试三种契约把 /scan 落到 commit。
      A) 顶层拍扁 + source/scan_ref
      B) 顶层拍扁 ctx（不嵌套 data）
      C) tokens 用 dict（不是 list）
    命中任意一个 committed=true 即可。
    """
    tries = []

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # A) 顶层拍扁 + source/scan_ref
        payload_A = {
            "node": "receive",
            "mode": "commit",
            "source": "api",
            "scan_ref": "DBG-REF-A",  # 很多实现会使用这个当 ref
            "warehouse_id": 1,
            "sku": "SKU-001",
            "qty": 10,
            "batch_code": "B20251012-A",
            "production_date": "2025-09-01",
            "expiry_date": "2026-09-01",
            "ref": "PO-DBG-A",
            "ref_line": 1,
        }
        rA = await ac.post("/scan", json=payload_A)
        tries.append(("A", rA.status_code, rA.text))
        committed = False
        try:
            committed = bool(rA.json().get("committed"))
        except Exception:
            committed = False
        if committed:
            print("\n[SCAN-DEBUG/A] status:", rA.status_code)
            print("[SCAN-DEBUG/A] body:", rA.text)
            assert committed is True
            return

        # B) 顶层拍扁 ctx （把 ctx 字段直接平铺）
        payload_B = {
            "node": "receive",
            "mode": "commit",
            "source": "api",
            "warehouse_id": 1,
            "ref": "PO-DBG-B",
            "ref_line": 1,
            "sku": "SKU-001",
            "qty": 10,
            "batch_code": "B20251012-A",
            "production_date": "2025-09-01",
            "expiry_date": "2026-09-01",
        }
        rB = await ac.post("/scan", json=payload_B)
        tries.append(("B", rB.status_code, rB.text))
        try:
            committed = bool(rB.json().get("committed"))
        except Exception:
            committed = False
        if committed:
            print("\n[SCAN-DEBUG/B] status:", rB.status_code)
            print("[SCAN-DEBUG/B] body:", rB.text)
            assert committed is True
            return

        # C) tokens 用 dict（不是 list）
        payload_C = {
            "node": "receive",
            "mode": "commit",
            "source": "api",
            "tokens": {
                "SKU": "SKU-001",
                "QTY": 10,
                "BATCH": "B20251012-A",
                "MFG": "2025-09-01",
                "EXP": "2026-09-01",
                "WH": 1,
                "REF": "PO-DBG-C",
                "LINE": 1,
            },
        }
        rC = await ac.post("/scan", json=payload_C)
        tries.append(("C", rC.status_code, rC.text))
        try:
            committed = bool(rC.json().get("committed"))
        except Exception:
            committed = False
        if committed:
            print("\n[SCAN-DEBUG/C] status:", rC.status_code)
            print("[SCAN-DEBUG/C] body:", rC.text)
            assert committed is True
            return

    # 如果三种都未命中，集中打印所有尝试，便于你或我继续对齐契约
    for tag, st, body in tries:
        print(f"\n[SCAN-DEBUG/{tag}] status:", st)
        print(f"[SCAN-DEBUG/{tag}] body:", body)
    assert False, "scan entry 未命中 commit 契约（A/B/C 皆未生效）；请据打印响应继续补全字段。"
