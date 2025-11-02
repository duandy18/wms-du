# tests/services/test_scan_putaway.py
import pytest
from sqlalchemy import text

pytestmark = [pytest.mark.grp_flow, pytest.mark.grp_scan]

from app.gateway.scan_putaway import scan_putaway_commit
from app.services.stock_service import StockService


async def _get_qty(session, item_id: int, wh: int, loc: int, batch_code: str) -> int:
    row = (
        await session.execute(
            text(
                """
        SELECT COALESCE(qty,0)::bigint
        FROM stocks
        WHERE item_id=:i AND warehouse_id=:w AND location_id=:l AND batch_code=:b
        """
            ),
            {"i": item_id, "w": wh, "l": loc, "b": batch_code},
        )
    ).first()
    return int(row[0]) if row else 0


async def _seed_stage_by_service(session, stage_id: int, batch_code: str, qty: int) -> None:
    """
    用服务层口径正式造货（最稳）：确保 batches、stocks、batch_id、台账等全部一致。
    """
    svc = StockService()
    await svc.adjust(
        session=session,
        item_id=1,  # 基线夹具已有 item_id=1
        location_id=stage_id,  # 源位（STAGE）
        delta=qty,  # 入库正腿
        reason="INBOUND",
        ref=f"SEED:{batch_code}",
        batch_code=batch_code,
    )
    await session.commit()


@pytest.mark.asyncio
async def test_scan_putaway_probe(session, monkeypatch):
    """
    保存点探活：从 STAGE → 目标 LOC:1，执行后回滚不落账。
    源位库存通过服务层造货，保证 FEFO 可见。
    """
    # 查 STAGE 位 id
    stage_id_row = (
        await session.execute(
            text("SELECT id FROM locations WHERE warehouse_id=1 AND code='01S9000000'")
        )
    ).first()
    assert stage_id_row, "STAGE location missing, seed locations first"
    stage_id = int(stage_id_row[0])

    # 源位造货（服务层）
    await _seed_stage_by_service(session, stage_id, "B-STAGE", 10)

    monkeypatch.delenv("SCAN_REAL_PUTAWAY", raising=False)  # 探活
    monkeypatch.setenv("SCAN_STAGE_LOCATION_ID", str(stage_id))

    before_src = await _get_qty(session, 1, 1, stage_id, "B-STAGE")
    before_dst = await _get_qty(session, 1, 1, 1, "B-STAGE")

    payload = {
        "device_id": "RF01",
        "operator": "tester",
        "barcode": "LOC:1",  # 目标库位（id=1）
        "mode": "putaway",
        "item_id": 1,
        "qty": 3,
        "ctx": {"warehouse_id": 1},
    }

    out = await scan_putaway_commit(session, payload)

    after_src = await _get_qty(session, 1, 1, stage_id, "B-STAGE")
    after_dst = await _get_qty(session, 1, 1, 1, "B-STAGE")

    assert out["source"] == "scan_putaway_commit"
    assert out["result"]["status"] in ("probe_ok", "ok")
    # 探活不落账
    assert after_src == before_src
    assert after_dst == before_dst


@pytest.mark.asyncio
async def test_scan_putaway_real_commit(session, monkeypatch):
    """
    真动作：从 STAGE → 目标 LOC:1，实际扣源加目标，三账一致性由护栏保证。
    """
    # 查 STAGE 位
    stage_id_row = (
        await session.execute(
            text("SELECT id FROM locations WHERE warehouse_id=1 AND code='01S9000000'")
        )
    ).first()
    assert stage_id_row, "STAGE location missing, seed locations first"
    stage_id = int(stage_id_row[0])

    # 源位造货（服务层）
    await _seed_stage_by_service(session, stage_id, "B-STAGE", 10)

    monkeypatch.setenv("SCAN_REAL_PUTAWAY", "1")
    monkeypatch.setenv("SCAN_STAGE_LOCATION_ID", str(stage_id))

    before_src = await _get_qty(session, 1, 1, stage_id, "B-STAGE")
    before_dst = await _get_qty(session, 1, 1, 1, "B-STAGE")

    payload = {
        "device_id": "RF01",
        "operator": "tester",
        "barcode": "LOC:1",  # 目标库位（id=1）
        "mode": "putaway",
        "item_id": 1,
        "qty": 4,
        "ctx": {"warehouse_id": 1},
    }

    out = await scan_putaway_commit(session, payload)

    after_src = await _get_qty(session, 1, 1, stage_id, "B-STAGE")
    after_dst = await _get_qty(session, 1, 1, 1, "B-STAGE")

    assert out["source"] == "scan_putaway_commit"
    assert out["result"]["status"] == "ok"
    assert (before_src - after_src) == 4
    assert (after_dst - before_dst) == 4
