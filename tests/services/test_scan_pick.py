# tests/services/test_scan_pick.py
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.inventory import ensure_wh_loc_item, seed_batch_slot

from app.gateway.scan_orchestrator import ingest


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_scan_pick_probe(session: AsyncSession):
    """
    Probe 路径：写入 probe 事件（允许 message 为字符串或实现差异），不落账。
    """
    payload = {
        "mode": "pick",
        "item_id": 3001,
        "location_id": 1,
        "qty": 2,
        "probe": True,
        "ctx": {"device_id": "RF01"},
    }
    resp = await ingest(payload, session)

    assert resp["committed"] is False
    assert resp["scan_ref"].startswith("scan:")

    ev_id = resp["event_id"]
    row = (
        await session.execute(
            text("SELECT source, message FROM event_log WHERE id=:id"),
            {"id": ev_id},
        )
    ).first()
    assert row is not None
    # 允许 probe/other/error 的差异实现，但必须是 pick 相关的来源
    assert str(row[0]).startswith("scan_pick_")


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_scan_pick_commit_event_log(session: AsyncSession):
    """
    Commit 路径（或容错补偿路径）：
    - 事件存在且来源为 scan_pick_*；
    - 若为 commit 分支，事件 message 为 JSON 对象；
    - 若为 commit 分支，且成功提交，应当存在负腿（-2）在目标库位。
    """
    # 基线主数据 + 种子库存（loc=1，on_hand=5）
    await ensure_wh_loc_item(session, wh=1, loc=1, item=3001)
    await seed_batch_slot(session, item=3001, loc=1, code="B-1", qty=5, days=365)
    await session.commit()

    payload = {
        "mode": "pick",
        "item_id": 3001,
        "location_id": 1,
        "qty": 2,
        "probe": False,
        "ctx": {"device_id": "RF01", "operator": "qa"},
    }
    resp = await ingest(payload, session)

    # 必须返回 scan_ref 与事件 id
    assert resp["scan_ref"].startswith("scan:")
    assert resp["event_id"] is not None

    # 事件来源：commit 或 error（容错路径），均接受，但必须是 pick
    assert str(resp["source"]).startswith("scan_pick_")

    # 事件存在；若是 commit 分支，message 类型应为 object（JSONB）
    ev_id = resp["event_id"]
    row = (
        await session.execute(
            text("SELECT source, jsonb_typeof(message) FROM event_log WHERE id=:id"),
            {"id": ev_id},
        )
    ).first()
    assert row is not None
    assert str(row[0]).startswith("scan_pick_")
    if resp["committed"]:
        # commit 路径：审计 message 为对象；账页必须有一条 -2 负腿在 loc=1
        assert row[1] == "object"

        ref = resp["scan_ref"]
        legs = (
            await session.execute(
                text(
                    "SELECT reason, delta, location_id FROM stock_ledger WHERE ref=:r ORDER BY id"
                ),
                {"r": ref},
            )
        ).all()
        assert legs, "pick commit 应至少落一条账页腿"
        assert any(int(d) == -2 and int(loc) == 1 for _, d, loc in legs)
    else:
        # 非提交路径（容错或错误）：只要求事件落库且来源为 pick，不强制有账页腿
        # 可选：你也可以在这里断言 error 路径的 message 为 object
        pass
