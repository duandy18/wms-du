import pytest

pytest.skip(
    "legacy outbound_v2/event_gateway tests (disabled on v2 baseline)", allow_module_level=True
)

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.inventory import ensure_wh_loc_item, seed_batch_slot

from app.services.outbound_v2_service import OutboundV2LineIn, OutboundV2Service

UTC = timezone.utc


async def _get_recommended_batch(session: AsyncSession, wh_id: int, item_id: int) -> str | None:
    """
    使用与 OutboundV2Service.commit 中相同的 SQL（基于 expiry_date），
    计算当前库存下 (warehouse_id, item_id) 的推荐批次。
    """
    rows = await session.execute(
        text(
            """
            SELECT b.batch_code,
                   b.expiry_date
              FROM batches b
              JOIN stocks s
                ON s.item_id = b.item_id
               AND s.warehouse_id = b.warehouse_id
               AND s.batch_code = b.batch_code
             WHERE b.warehouse_id = :wh
               AND b.item_id      = :item
               AND s.qty          > 0
             ORDER BY b.expiry_date ASC NULLS LAST,
                      b.batch_code ASC
             LIMIT 1
            """
        ),
        {"wh": wh_id, "item": item_id},
    )
    row = rows.first()
    return str(row[0]) if row is not None else None


async def _get_all_batches(session: AsyncSession, wh_id: int, item_id: int) -> list[str]:
    rows = await session.execute(
        text(
            """
            SELECT DISTINCT b.batch_code
              FROM batches b
              JOIN stocks s
                ON s.item_id = b.item_id
               AND s.warehouse_id = b.warehouse_id
               AND s.batch_code = b.batch_code
             WHERE b.warehouse_id = :wh
               AND b.item_id      = :item
               AND s.qty          > 0
             ORDER BY b.batch_code ASC
            """
        ),
        {"wh": wh_id, "item": item_id},
    )
    return [str(r[0]) for r in rows.fetchall()]


@pytest.mark.asyncio
async def test_outbound_v2_uses_recommended_batch_no_deviation(
    db_session_like_pg: AsyncSession,
):
    """
    软 FEFO 场景 1：使用推荐批次时，不应写 FEFO_DEVIATION 审计记录。
    """
    session = db_session_like_pg
    platform = "PDD"
    shop_id = "S-FEFO-1"
    trace_id = "TRACE-FEFO-OK-1"
    ref = "OUT-FEFO-OK-1"

    wh_id = 1
    item_id = 91001

    await ensure_wh_loc_item(session, wh=wh_id, loc=wh_id, item=item_id)

    # 根据 days=10 / 30 写入 expiry_date
    await seed_batch_slot(
        session,
        item=item_id,
        loc=wh_id,
        code="B-NEAR",
        qty=10,
        days=10,
    )
    await seed_batch_slot(
        session,
        item=item_id,
        loc=wh_id,
        code="B-FAR",
        qty=10,
        days=30,
    )
    await session.commit()

    # FEFO 推荐批次（按 expiry_date 排）应为 B-NEAR
    recommended = await _get_recommended_batch(session, wh_id, item_id)
    assert recommended == "B-NEAR", f"推荐批次应为 B-NEAR，但实际为: {recommended!r}"

    svc = OutboundV2Service()

    occurred_at = datetime.now(UTC)
    result = await svc.commit(
        session=session,
        trace_id=trace_id,
        platform=platform,
        shop_id=shop_id,
        ref=ref,
        external_order_ref=None,
        lines=[
            OutboundV2LineIn(
                warehouse_id=wh_id,
                item_id=item_id,
                batch_code=recommended,
                qty=5,
            )
        ],
        occurred_at=occurred_at,
    )
    assert result["status"] == "OK"
    await session.commit()

    # 不应存在 FEFO_DEVIATION 审计记录
    rows = await session.execute(
        text(
            """
            SELECT meta
              FROM audit_events
             WHERE category = 'OUTBOUND'
               AND ref      = :ref
               AND (meta->>'event') = 'FEFO_DEVIATION'
            """
        ),
        {"ref": ref},
    )
    metas = rows.fetchall()
    assert metas == [], f"不应存在 FEFO_DEVIATION 记录，但查到: {metas!r}"


@pytest.mark.asyncio
async def test_outbound_v2_records_fefo_deviation_when_skipping_recommended_batch(
    db_session_like_pg: AsyncSession,
):
    """
    软 FEFO 场景 2：完全跳过推荐批次时，应写 FEFO_DEVIATION 审计记录。
    """
    session = db_session_like_pg
    platform = "PDD"
    shop_id = "S-FEFO-2"
    trace_id = "TRACE-FEFO-DEV-1"
    ref = "OUT-FEFO-DEV-1"

    wh_id = 1
    item_id = 91002

    await ensure_wh_loc_item(session, wh=wh_id, loc=wh_id, item=item_id)

    await seed_batch_slot(
        session,
        item=item_id,
        loc=wh_id,
        code="B-NEAR",
        qty=10,
        days=10,
    )
    await seed_batch_slot(
        session,
        item=item_id,
        loc=wh_id,
        code="B-FAR",
        qty=10,
        days=30,
    )
    await session.commit()

    # 推荐批次 & 所有批次
    recommended = await _get_recommended_batch(session, wh_id, item_id)
    assert recommended == "B-NEAR", f"推荐批次应为 B-NEAR，但实际为: {recommended!r}"
    all_codes = await _get_all_batches(session, wh_id, item_id)
    assert set(all_codes) == {"B-NEAR", "B-FAR"}

    non_recommended = "B-FAR"

    svc = OutboundV2Service()

    occurred_at = datetime.now(UTC)
    result = await svc.commit(
        session=session,
        trace_id=trace_id,
        platform=platform,
        shop_id=shop_id,
        ref=ref,
        external_order_ref=None,
        lines=[
            OutboundV2LineIn(
                warehouse_id=wh_id,
                item_id=item_id,
                batch_code=non_recommended,
                qty=5,
            )
        ],
        occurred_at=occurred_at,
    )
    assert result["status"] == "OK"
    await session.commit()

    # 查询 FEFO_DEVIATION 审计记录
    rows = await session.execute(
        text(
            """
            SELECT meta
              FROM audit_events
             WHERE category = 'OUTBOUND'
               AND ref      = :ref
               AND (meta->>'event') = 'FEFO_DEVIATION'
            """
        ),
        {"ref": ref},
    )
    metas = [r[0] for r in rows.fetchall()]
    assert metas, "应当至少有一条 FEFO_DEVIATION 审计记录"

    meta0 = metas[0]
    if isinstance(meta0, str):
        import json as _json

        meta0 = _json.loads(meta0)

    assert meta0.get("recommended_batch") == "B-NEAR"
    used_batches = meta0.get("used_batches") or []
    assert non_recommended in used_batches
