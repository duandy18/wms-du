import inspect
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.asyncio]


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


# ----------------------
# generic fresh session helpers
# ----------------------
async def _scalar_fresh(engine, sql: str, params: dict):
    async with AsyncSession(bind=engine, expire_on_commit=False) as s:
        try:
            return await s.scalar(text(sql), params)
        except DBAPIError:
            await s.rollback()
            return await s.scalar(text(sql), params)


async def _row_fresh(engine, sql: str, params: dict):
    async with AsyncSession(bind=engine, expire_on_commit=False) as s:
        try:
            res = await s.execute(text(sql), params)
            return res.first()
        except DBAPIError:
            await s.rollback()
            res = await s.execute(text(sql), params)
            return res.first()


async def _exec_fresh(engine, sql: str, params: dict):
    async with AsyncSession(bind=engine, expire_on_commit=False) as s:
        await s.execute(text(sql), params)
        await s.commit()


# ----------------------
# stock state helpers
# ----------------------
async def _ensure_location(engine, loc_id: int, wh_id: int = 1):
    await _exec_fresh(
        engine,
        "INSERT INTO warehouses (id, name) VALUES (:w, 'AUTO-WH') ON CONFLICT (id) DO NOTHING",
        {"w": wh_id},
    )
    await _exec_fresh(
        engine,
        "INSERT INTO locations (id, name, warehouse_id) VALUES (:i, :n, :w) ON CONFLICT (id) DO NOTHING",
        {"i": loc_id, "n": f"A-{loc_id:04d}", "w": wh_id},
    )


async def _get_qty(engine, *, item_id: int, loc_id: int) -> int:
    v = await _scalar_fresh(
        engine,
        "SELECT COALESCE(qty,0) FROM stocks WHERE item_id=:i AND location_id=:l",
        {"i": item_id, "l": loc_id},
    )
    return int(v or 0)


async def _sum_qty(engine, *, item_id: int) -> int:
    v = await _scalar_fresh(engine, "SELECT COALESCE(SUM(qty),0) FROM stocks WHERE item_id=:i", {"i": item_id})
    return int(v or 0)


async def _pick_src_location_for_item(engine, *, item_id: int, min_qty: int) -> int:
    row = await _row_fresh(
        engine,
        """
        SELECT location_id, qty
        FROM stocks
        WHERE item_id=:i
        ORDER BY qty DESC, location_id ASC
        LIMIT 1
        """,
        {"i": item_id},
    )
    if not row:
        raise AssertionError("没有可用库存作为上架源位")
    loc_id, qty = int(row[0]), int(row[1])
    # 不强制必须 >= min_qty，部分实现可能在 receive 时拆分批次
    return loc_id


# ----------------------
# build source stock by using InboundService
# ----------------------
async def _receive_to_make_stock(engine, *, sku: str, qty: int, stage_location_id: int | None = None) -> int:
    """用 InboundService 造货；返回 item_id。"""
    from app.services.inbound_service import InboundService

    ref, ref_line = _unique("INB"), 1

    async with AsyncSession(bind=engine, expire_on_commit=False) as s:
        svc = InboundService()
        fn = getattr(svc, "receive")
        kwargs = dict(session=s, sku=sku, qty=qty, ref=ref, ref_line=ref_line)
        if stage_location_id is not None:
            kwargs["stage_location_id"] = stage_location_id

        async with s.begin():
            res = fn(**kwargs)
            if inspect.isawaitable(res):
                res = await res

        if isinstance(res, dict) and "item_id" in res:
            return int(res["item_id"])

        row = await s.execute(text("SELECT id FROM items WHERE sku=:sku LIMIT 1"), {"sku": sku})
        got = row.first()
        if not got:
            raise AssertionError("造货后无法解析 item_id")
        return int(got[0])


# ----------------------
# Putaway adapters（支持两类幂等：同 task_id；或同 ref/ref_line）
# ----------------------
def _bind_putaway_kwargs(fn, *, session, item_id, src_loc, dst_loc, qty, ref, ref_line):
    """按函数签名自适配参数名（from_/to_ 优先；回退 src_/dst_ 等变体）"""
    sig = inspect.signature(fn)
    params = sig.parameters
    kw = {}

    # session/db/sess
    for name in ("session", "db", "sess"):
        if name in params:
            kw[name] = session
            break

    # 位置参数命名优先级：from_/to_ → src_/dst_ → 其它合理变体
    if "from_location_id" in params:
        kw["from_location_id"] = src_loc
    elif "src_location_id" in params:
        kw["src_location_id"] = src_loc
    elif "src_loc" in params:
        kw["src_loc"] = src_loc

    if "to_location_id" in params:
        kw["to_location_id"] = dst_loc
    elif "dst_location_id" in params:
        kw["dst_location_id"] = dst_loc
    elif "dst_loc" in params:
        kw["dst_loc"] = dst_loc

    # item_id
    if "item_id" in params:
        kw["item_id"] = item_id

    # 数量可能叫 qty/quantity/move_qty
    if "qty" in params:
        kw["qty"] = qty
    elif "quantity" in params:
        kw["quantity"] = qty
    elif "move_qty" in params:
        kw["move_qty"] = qty

    # 幂等参考
    if "ref" in params:
        kw["ref"] = ref
    if "ref_line" in params:
        kw["ref_line"] = ref_line

    return kw


async def _call_putaway_twice(
    engine,
    *,
    item_id: int,
    src_loc: int,
    dst_loc: int,
    qty: int,
    _fixed_key: str | None = None,
):
    """
    幂等测试：
    - 若存在任务流：create_task 一次，putaway 同一 task_id 执行两次；
    - 否则：直接 putaway，用同一个 (ref, ref_line) 连续执行两次。
    为了保证跨多次调用也幂等，这里固定业务键：
      biz_key = _fixed_key or f"PUT-{item_id}-{src_loc}-{dst_loc}-{qty}"
    """
    from app.services.putaway_service import PutawayService

    biz_key = _fixed_key or f"PUT-{item_id}-{src_loc}-{dst_loc}-{qty}"
    ref, ref_line = biz_key, 1

    async with AsyncSession(bind=engine, expire_on_commit=False) as s:
        svc = PutawayService()

        # 方案1：任务流；同一 task_id 两次执行
        if hasattr(svc, "create_task") and callable(getattr(svc, "create_task")) and hasattr(svc, "putaway"):
            # 使用稳定的 ref/ref_line 以便服务端自行实现 create_task 幂等复用
            async with s.begin():
                task_id = await svc.create_task(
                    session=s,
                    item_id=item_id,
                    src_location_id=src_loc,
                    dst_location_id=dst_loc,
                    qty=qty,
                    ref=ref,
                    ref_line=ref_line,
                )
            # 第一次执行
            async with s.begin():
                await svc.putaway(session=s, task_id=task_id)
            # 第二次执行（同一个 task_id）
            async with s.begin():
                await svc.putaway(session=s, task_id=task_id)
            return

        # 方案2：直接 putaway；相同的 (ref, ref_line) 两次执行
        if not hasattr(svc, "putaway") or not callable(getattr(svc, "putaway")):
            raise AssertionError("PutawayService.putaway 不存在或不可调用")

        fn = getattr(svc, "putaway")
        kw = _bind_putaway_kwargs(
            fn, session=s, item_id=item_id, src_loc=src_loc, dst_loc=dst_loc, qty=qty, ref=ref, ref_line=ref_line
        )

        # 第一次
        async with s.begin():
            res = fn(**kw)
            if inspect.isawaitable(res):
                await res
        # 第二次（同幂等键）
        async with s.begin():
            res = fn(**kw)
            if inspect.isawaitable(res):
                await res


# ----------------------
# the test
# ----------------------
async def test_putaway_binds_location_and_is_idempotent(session, _baseline_seed, _db_clean):
    """
    上架：源位减少、目标位增加、总量不变；重复执行幂等
    """
    engine = session.bind
    if engine is None:
        pytest.fail("session.bind is None")

    # 1) 造货到一个“源位”
    sku = "ITEM-PA"
    qty = 5

    item_id = await _receive_to_make_stock(engine, sku=sku, qty=qty)
    src_loc = await _pick_src_location_for_item(engine, item_id=item_id, min_qty=qty)

    # 创建一个不同的目标位
    dst_loc = 9999
    if dst_loc == src_loc:
        dst_loc += 1
    await _ensure_location(engine, dst_loc)

    # 记录搬运前状态
    total_before = await _sum_qty(engine, item_id=item_id)
    src_before = await _get_qty(engine, item_id=item_id, loc_id=src_loc)
    dst_before = await _get_qty(engine, item_id=item_id, loc_id=dst_loc)

    # 2) putaway：执行两次（同 task_id 或同 ref/ref_line），固定幂等键
    stable_key = f"PUT-{item_id}-{src_loc}-{dst_loc}-{qty}"
    await _call_putaway_twice(
        engine, item_id=item_id, src_loc=src_loc, dst_loc=dst_loc, qty=qty, _fixed_key=stable_key
    )

    # 搬运后状态
    total_after = await _sum_qty(engine, item_id=item_id)
    src_after = await _get_qty(engine, item_id=item_id, loc_id=src_loc)
    dst_after = await _get_qty(engine, item_id=item_id, loc_id=dst_loc)

    # 断言：总量不变；源位减少 >= qty；目标位增加 >= qty
    assert total_after == total_before, "总库存应不变"
    assert src_before - src_after >= qty, f"源位未按期望减少：{src_before} -> {src_after}"
    assert dst_after - dst_before >= qty, f"目标位未按期望增加：{dst_before} -> {dst_after}"

    # 3) 幂等：再次调用（第三次/第四次）不应再改变状态
    before_third_src = await _get_qty(engine, item_id=item_id, loc_id=src_loc)
    before_third_dst = await _get_qty(engine, item_id=item_id, loc_id=dst_loc)
    before_third_total = await _sum_qty(engine, item_id=item_id)

    # 再执行一次（同幂等键，同 task_id/同 ref）应不变
    await _call_putaway_twice(
        engine, item_id=item_id, src_loc=src_loc, dst_loc=dst_loc, qty=qty, _fixed_key=stable_key
    )

    after_third_src = await _get_qty(engine, item_id=item_id, loc_id=src_loc)
    after_third_dst = await _get_qty(engine, item_id=item_id, loc_id=dst_loc)
    after_third_total = await _sum_qty(engine, item_id=item_id)

    assert (before_third_src, before_third_dst, before_third_total) == (
        after_third_src,
        after_third_dst,
        after_third_total,
    ), "重复执行不应再改变状态（幂等）"
