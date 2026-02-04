# tests/services/pick/_seed_order_items.py
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError, ProgrammingError


async def pick_any_item_id(session: AsyncSession) -> int:
    """
    从测试基线里选择一个 item_id。
    """
    row = await session.execute(text("SELECT id FROM items ORDER BY id ASC LIMIT 1"))
    v = row.scalar_one_or_none()
    if v is None:
        raise RuntimeError("no items in test baseline")
    return int(v)


async def ensure_order_has_items(
    session: AsyncSession,
    *,
    order_id: int,
    item_id: int,
    qty: int,
) -> None:
    """
    为 from-order 创建 pick_task 的前置条件：订单必须有商品行。

    关键点：Postgres 一旦某条 INSERT 触发错误（如 NOT NULL / UndefinedColumn），
    当前事务就会进入 aborted 状态，后续语句全部失败，直到 rollback。

    因此这里每次“试插入”都用 SAVEPOINT（begin_nested）隔离：
    - 失败只回滚到 savepoint，不污染外层事务
    - 允许继续尝试其他列组合，兼容不同阶段的 order_items schema

    ✅ Phase 5 迁移后的关键收口：
    - order_items 上若存在 NOT NULL 且无默认值的累积字段（如 shipped_qty），
      测试 helper 必须在创建时显式初始化（通常为 0）。
    - 严禁再使用“最小三列插入”作为兜底，因为它会在新 schema 下明确非法。
    """
    q = int(qty)
    if q <= 0:
        q = 1

    params = {"oid": int(order_id), "iid": int(item_id), "q": int(q)}

    async def _try(sql: str) -> bool:
        """
        返回 True 表示“本次尝试已满足前置条件”：
        - 插入成功
        - 或触发唯一冲突被 DO NOTHING 吞掉（代表行已存在）
        """
        try:
            async with session.begin_nested():  # SAVEPOINT
                await session.execute(text(sql), params)
            return True
        except (ProgrammingError, IntegrityError):
            return False

    # 1) 优先：带 shipped_qty / picked_qty / reserved_qty（常见且可能 NOT NULL）
    ok = await _try(
        """
        INSERT INTO order_items (order_id, item_id, qty, shipped_qty, picked_qty, reserved_qty)
        VALUES (:oid, :iid, :q, 0, 0, 0)
        ON CONFLICT DO NOTHING
        """
    )
    if ok:
        return

    # 2) 次优：只带 shipped_qty（你当前 schema 明确要求其 NOT NULL）
    ok = await _try(
        """
        INSERT INTO order_items (order_id, item_id, qty, shipped_qty)
        VALUES (:oid, :iid, :q, 0)
        ON CONFLICT DO NOTHING
        """
    )
    if ok:
        return

    # 3) 终局兜底（schema 驱动）：自动探测 order_items 上“NOT NULL 且无默认值”的列，
    #    为其提供可接受的初始化字面量（通常是 0 / false / now() / current_date / '{}'）。
    async def _insert_with_required_not_null_defaults() -> None:
        rows = await session.execute(
            text(
                """
                SELECT
                  column_name,
                  data_type,
                  udt_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'order_items'
                  AND is_nullable = 'NO'
                  AND column_default IS NULL
                ORDER BY ordinal_position
                """
            )
        )
        required = [(str(r[0]), str(r[1]), str(r[2])) for r in rows.all()]

        base_cols = {"order_id", "item_id", "qty"}

        extra_cols_sql: list[str] = []
        extra_vals_sql: list[str] = []

        def _literal_for(col: str, data_type: str, udt_name: str) -> str:
            if data_type in {
                "smallint",
                "integer",
                "bigint",
                "numeric",
                "real",
                "double precision",
                "decimal",
            }:
                return "0"
            if data_type == "boolean":
                return "false"
            if data_type in {"timestamp without time zone", "timestamp with time zone"}:
                return "now()"
            if data_type == "date":
                return "current_date"
            if data_type in {"json", "jsonb"}:
                return "'{}'::jsonb" if data_type == "jsonb" or udt_name == "jsonb" else "'{}'::json"
            raise RuntimeError(
                "order_items requires NOT NULL column without default that helper cannot safely init: "
                f"{col} (data_type={data_type}, udt_name={udt_name}). "
                "Please extend mapping in tests/services/pick/_seed_order_items.py"
            )

        for col, data_type, udt_name in required:
            if col in base_cols:
                continue
            extra_cols_sql.append(col)
            extra_vals_sql.append(_literal_for(col, data_type, udt_name))

        cols = ["order_id", "item_id", "qty", *extra_cols_sql]
        vals = [":oid", ":iid", ":q", *extra_vals_sql]

        sql = f"""
        INSERT INTO order_items ({", ".join(cols)})
        VALUES ({", ".join(vals)})
        ON CONFLICT DO NOTHING
        """

        async with session.begin_nested():
            await session.execute(text(sql), params)

    await _insert_with_required_not_null_defaults()
