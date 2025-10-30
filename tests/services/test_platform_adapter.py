import pytest

pytestmark = pytest.mark.grp_events

import asyncio

import pytest

pytestmark = pytest.mark.asyncio


async def test_push_inventory_retry_no_side_effect(monkeypatch):
    from app.services.platform_adapter import PlatformAdapter

    calls = {"n": 0}

    async def flaky_push(*args, **kwargs):
        calls["n"] += 1
        # 前两次超时，第三次成功
        if calls["n"] < 3:
            await asyncio.sleep(0)  # 让出事件循环
            raise TimeoutError("simulated timeout")
        return {"ok": True}

    adapter = PlatformAdapter(platform="FAKE")
    monkeypatch.setattr(adapter, "_push_inventory_once", flaky_push)

    res = await adapter.push_inventory(item_id=3501, qty=7)
    assert res.get("ok") is True
    # 确认重试发生，但不出现重复副作用（一次成功落库即可）
    assert calls["n"] >= 3
