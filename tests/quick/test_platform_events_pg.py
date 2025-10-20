import asyncio

import pytest

from app.services.platform_events import handle_event_batch


@pytest.mark.asyncio
async def test_handle_pdd_event_batch(monkeypatch):
    """简单验证平台事件批处理框架可执行。"""
    events = [
        {"platform": "pdd", "order_sn": "P12345", "status": "PAID"},
        {"platform": "pdd", "order_sn": "P99999", "status": "CANCEL"},
    ]
    await handle_event_batch(events)
    # TODO: 后续断言 Outbound 任务状态或日志输出
    assert True
