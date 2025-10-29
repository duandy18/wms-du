import pytest
from datetime import date, timedelta
pytestmark = pytest.mark.asyncio

async def _seed(session, item_id=1, wh=1):
    from sqlalchemy import text
    # 两个批次：一个临期优先
    today = date.today()
    rows = [
        (item_id, wh, 1, "B1", today + timedelta(days=2), 3),
        (item_id, wh, 1, "B2", today + timedelta(days=10), 5),
    ]
    for i,w,l,c,e,q in rows:
        await session.execute(text("""
            INSERT INTO batches(item_id, warehouse_id, location_id, batch_code, expire_at)
            VALUES (:i,:w,:l,:c,:e) ON CONFLICT DO NOTHING
        """), {"i": i,"w": w,"l": l,"c": c,"e": e})
        await session.execute(text("""
            INSERT INTO stocks(item_id, warehouse_id, location_id, batch_code, qty)
            VALUES (:i,:w,:l,:c,:q)
            ON CONFLICT (item_id, warehouse_id, location_id, batch_code)
            DO UPDATE SET qty = stocks.qty + EXCLUDED.qty
        """), {"i": i,"w": w,"l": l,"c": c,"q": q})
    await session.commit()

async def test_fefo_reserve_then_cancel(session):
    from app.services.order_service import OrderService
    await _seed(session)
    svc = OrderService()

    oid = await svc.create_order(session=session, item_id=1, warehouse_id=1, qty=4, client_ref="REF-1")
    # 预期：先占用 B1(3) 再从 B2(1)
    res = await svc.reserve(session=session, order_id=oid)
    assert res.reserved_qty == 4

    await svc.cancel(session=session, order_id=oid)
    # 取消后库存应回滚（总和恢复到 8）
    from sqlalchemy import text
    s = await session.execute(text("""
        SELECT SUM(qty) FROM stocks WHERE item_id=1 AND warehouse_id=1
    """))
    assert int(s.scalar() or 0) == 8
