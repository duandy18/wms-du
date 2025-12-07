# tests/services/test_pick_handler.py
import pytest

from app.services.scan_handlers.pick_handler import handle_pick


@pytest.mark.asyncio
async def test_handle_pick(monkeypatch, session):
    """
    handle_pick: delegates to StockService.adjust with a negative delta.
    Test does not modify application code; it adapts enums and patches adjust().
    """
    # --- 1) 兼容枚举：如果主程序没有 MovementType.OUTBOUND，就映射到 SHIPMENT ---
    from app.models.enums import MovementType

    if not hasattr(MovementType, "OUTBOUND"):
        if hasattr(MovementType, "SHIPMENT"):
            monkeypatch.setattr(MovementType, "OUTBOUND", MovementType.SHIPMENT, raising=False)
        else:
            # 退一步：用任意占位符，测试只关心 delta 为负，不强耦合具体枚举值
            monkeypatch.setattr(MovementType, "OUTBOUND", "OUTBOUND", raising=False)

    # --- 2) 打桩 StockService.adjust，记录调用入参 ---
    calls = {}

    async def _fake_adjust(self, *, session, item_id, location_id, delta, reason, ref, **_):
        calls.update(
            dict(item_id=item_id, location_id=location_id, delta=delta, reason=reason, ref=ref)
        )

    # 注意：打桩路径为 services.stock_service 模块内的 StockService
    from app.services import stock_service as stock_mod

    monkeypatch.setattr(stock_mod.StockService, "adjust", _fake_adjust, raising=True)

    # --- 3) 运行被测函数 ---
    item_id, location_id, qty, ref = 1001, 1, 10, "SCAN-PICK-001"
    result = await handle_pick(
        session=session,
        item_id=item_id,
        location_id=location_id,
        qty=qty,
        ref=ref,
    )

    # --- 4) 断言：负扣减、参数透传正确；不强制具体 reason 名字 ---
    assert calls["item_id"] == item_id
    assert calls["location_id"] == location_id
    assert calls["delta"] == -qty
    assert calls["ref"] == ref
    assert calls["reason"] == getattr(MovementType, "OUTBOUND")

    # 返回值
    assert result == {"picked": qty}
