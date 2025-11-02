# app/services/channel_inventory_service.py
from __future__ import annotations

from typing import Optional, Dict, Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ChannelInventoryService:
    """
    维护渠道侧 reserved_qty（支持 ref 幂等），与仓内库存/台账解耦。
    返回值统一为：{"reserved_total": int, "idempotent": bool}
    """

    @staticmethod
    async def _ensure_row(session: AsyncSession, *, store_id: int, item_id: int) -> None:
        """确保 channel_inventory(store_id,item_id) 存在（不提交）。"""
        await session.execute(
            text("""
                INSERT INTO channel_inventory(store_id, item_id, reserved_qty)
                VALUES (:sid, :iid, 0)
                ON CONFLICT (store_id, item_id) DO NOTHING
            """),
            {"sid": int(store_id), "iid": int(item_id)},
        )

    @staticmethod
    async def adjust_reserved(
        session: AsyncSession,
        *,
        store_id: int,
        item_id: int,
        delta: int,
        ref: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        调整店铺层 reserved_qty（支持 ref 幂等）：
        - delta > 0 占用，delta < 0 释放；
        - 若提供 ref：同一 ref 重复调用将被忽略；
        - 返回 {"reserved_total": int, "idempotent": bool}
        """
        idempotent_hit = False

        tx_ctx = session.begin_nested() if session.in_transaction() else session.begin()
        async with tx_ctx:
            # 0) 幂等钥匙表（无迁移依赖，首次调用自动建表）
            if ref:
                await session.execute(text("""
                    CREATE TABLE IF NOT EXISTS channel_reserved_idem(
                        ref        TEXT PRIMARY KEY,
                        store_id   BIGINT,
                        item_id    BIGINT,
                        delta      INTEGER,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """))
                ins = await session.execute(
                    text("""
                        INSERT INTO channel_reserved_idem(ref, store_id, item_id, delta)
                        VALUES (:ref, :sid, :iid, :d)
                        ON CONFLICT (ref) DO NOTHING
                    """),
                    {"ref": ref, "sid": int(store_id), "iid": int(item_id), "d": int(delta)},
                )
                if ins.rowcount == 0:
                    idempotent_hit = True

            # 1) 确保目标行存在
            await ChannelInventoryService._ensure_row(session, store_id=store_id, item_id=item_id)

            # 2) 非幂等命中时执行调整（防负数）
            if not idempotent_hit and delta != 0:
                await session.execute(
                    text("""
                        UPDATE channel_inventory
                        SET reserved_qty = GREATEST(reserved_qty + :d, 0)
                        WHERE store_id=:sid AND item_id=:iid
                    """),
                    {"sid": int(store_id), "iid": int(item_id), "d": int(delta)},
                )

            # 3) 读取最新 reserved_total
            total = (
                await session.execute(
                    text("""
                        SELECT reserved_qty
                        FROM channel_inventory
                        WHERE store_id=:sid AND item_id=:iid
                    """),
                    {"sid": int(store_id), "iid": int(item_id)},
                )
            ).scalar_one_or_none() or 0

        await session.commit()
        return {"reserved_total": int(total), "idempotent": bool(idempotent_hit)}

    @staticmethod
    async def set_visible(
        session: AsyncSession,
        *,
        store_id: int,
        item_id: int,
        visible: int,
    ) -> None:
        """
        可见量写入（保留接口，不参与 B 组关键链路）。
        同时兼容两种列名：visible 优先；若存在 legacy 列 visible_qty，也一并更新。
        """
        v = int(max(visible, 0))

        tx_ctx = session.begin_nested() if session.in_transaction() else session.begin()
        async with tx_ctx:
            await ChannelInventoryService._ensure_row(session, store_id=store_id, item_id=item_id)

            # 写入 visible（若列存在）
            await session.execute(
                text("""
                    DO $$
                    BEGIN
                      IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_schema='public' AND table_name='channel_inventory' AND column_name='visible'
                      ) THEN
                        UPDATE channel_inventory
                        SET visible=:v
                        WHERE store_id=:sid AND item_id=:iid;
                      END IF;
                    END $$;
                """),
                {"sid": int(store_id), "iid": int(item_id), "v": v},
            )

            # 兼容写入 legacy 列 visible_qty（若存在）
            await session.execute(
                text("""
                    DO $$
                    BEGIN
                      IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_schema='public' AND table_name='channel_inventory' AND column_name='visible_qty'
                      ) THEN
                        UPDATE channel_inventory
                        SET visible_qty=:v
                        WHERE store_id=:sid AND item_id=:iid;
                      END IF;
                    END $$;
                """),
                {"sid": int(store_id), "iid": int(item_id), "v": v},
            )

        await session.commit()
