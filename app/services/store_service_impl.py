# app/services/store_service_impl.py
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class StoreService:
    """
    店铺档案与仓库绑定服务 + 最小 CRUD（实现体）。
    """

    # ------------------------------------------------------------------
    # 店铺 UPSERT（store 主数据，按 platform + shop_id）
    # ------------------------------------------------------------------
    @staticmethod
    async def ensure_store(
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        name: Optional[str] = None,
    ) -> int:
        plat = platform.upper()

        rec = await session.execute(
            text(
                """
                SELECT id
                  FROM stores
                 WHERE platform = :p
                   AND shop_id  = :s
                 LIMIT 1
                """
            ),
            {"p": plat, "s": shop_id},
        )
        row = rec.first()
        if row is not None:
            return int(row[0])

        ins = await session.execute(
            text(
                """
                INSERT INTO stores (platform, shop_id, name)
                VALUES (:p, :s, :n)
                ON CONFLICT (platform, shop_id) DO UPDATE
                SET name = COALESCE(EXCLUDED.name, stores.name)
                RETURNING id
                """
            ),
            {"p": plat, "s": shop_id, "n": name or f"{plat}-{shop_id}"},
        )
        new_id = ins.scalar()
        return int(new_id)

    # ------------------------------------------------------------------
    # 店 ↔ 仓 绑定
    # ------------------------------------------------------------------
    @staticmethod
    async def bind_warehouse(
        session: AsyncSession,
        *,
        store_id: int,
        warehouse_id: int,
        is_default: bool = False,
        priority: int = 100,
        is_top: Optional[bool] = None,
    ) -> None:
        """
        幂等绑定店铺与仓库。
        """
        if is_top is None:
            is_top = is_default

        # 若要设置主仓 / 默认仓，先清空同店其他记录的 is_top / is_default
        if is_top or is_default:
            await session.execute(
                text(
                    """
                    UPDATE store_warehouse
                       SET is_top = FALSE,
                           -- 只有在本次也是默认仓时，才清空其他记录的 is_default
                           is_default = CASE WHEN :def THEN FALSE ELSE is_default END,
                           updated_at = now()
                     WHERE store_id = :sid
                    """
                ),
                {"sid": store_id, "def": is_default},
            )

        await session.execute(
            text(
                """
                INSERT INTO store_warehouse (store_id, warehouse_id, is_top, is_default, priority)
                VALUES (:sid, :wid, :top, :def, :pri)
                ON CONFLICT (store_id, warehouse_id) DO UPDATE
                SET is_top     = EXCLUDED.is_top,
                    is_default = EXCLUDED.is_default,
                    priority   = EXCLUDED.priority,
                    updated_at = now()
                """
            ),
            {
                "sid": store_id,
                "wid": warehouse_id,
                "top": bool(is_top),
                "def": bool(is_default),
                "pri": int(priority),
            },
        )

    # ------------------------------------------------------------------
    # ✅ 新增：设置默认仓（只处理 is_default，不动 is_top/priority）
    # ------------------------------------------------------------------
    @staticmethod
    async def set_default_warehouse(
        session: AsyncSession,
        *,
        store_id: int,
        warehouse_id: int,
    ) -> None:
        """
        将某个已绑定仓设置为默认仓（唯一）。

        约束：
        - warehouse_id 必须已绑定到 store_warehouse，否则抛 ValueError
        - 不修改 is_top / priority
        """
        chk = await session.execute(
            text(
                """
                SELECT 1
                  FROM store_warehouse
                 WHERE store_id = :sid
                   AND warehouse_id = :wid
                 LIMIT 1
                """
            ),
            {"sid": store_id, "wid": warehouse_id},
        )
        if not chk.first():
            raise ValueError("该仓库未绑定到店铺，不能设为默认仓。")

        # 1) 清空同店其它默认仓
        await session.execute(
            text(
                """
                UPDATE store_warehouse
                   SET is_default = FALSE,
                       updated_at = now()
                 WHERE store_id = :sid
                """
            ),
            {"sid": store_id},
        )

        # 2) 设置目标仓为默认仓
        await session.execute(
            text(
                """
                UPDATE store_warehouse
                   SET is_default = TRUE,
                       updated_at = now()
                 WHERE store_id = :sid
                   AND warehouse_id = :wid
                """
            ),
            {"sid": store_id, "wid": warehouse_id},
        )

    # ------------------------------------------------------------------
    # 默认仓解析
    # ------------------------------------------------------------------
    @staticmethod
    async def resolve_default_warehouse(
        session: AsyncSession,
        *,
        store_id: int,
    ) -> Optional[int]:
        rec = await session.execute(
            text(
                """
                SELECT warehouse_id
                  FROM store_warehouse
                 WHERE store_id = :sid
                 ORDER BY is_top DESC,
                          is_default DESC,
                          priority ASC,
                          warehouse_id ASC
                 LIMIT 1
                """
            ),
            {"sid": store_id},
        )
        row = rec.first()
        return int(row[0]) if row else None

    @staticmethod
    async def resolve_default_warehouse_for_platform_shop(
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
    ) -> Optional[int]:
        plat = platform.upper()

        store_id = await StoreService.ensure_store(
            session,
            platform=plat,
            shop_id=shop_id,
            name=f"{plat}-{shop_id}",
        )

        return await StoreService.resolve_default_warehouse(session, store_id=store_id)

    # ------------------------------------------------------------------
    # 最小 CRUD（给 test_store_service 用）
    # ------------------------------------------------------------------
    async def create_store(
        self,
        session: AsyncSession,
        *,
        name: str,
        code: str,
        platform: str = "INTERNAL",
        shop_id: Optional[str] = None,
    ) -> int:
        plat = platform.upper()
        shop = shop_id or code

        row = await session.execute(
            text(
                """
                INSERT INTO stores (platform, shop_id, name)
                VALUES (:p, :s, :n)
                RETURNING id
                """
            ),
            {"p": plat, "s": shop, "n": name},
        )
        store_id = row.scalar()
        return int(store_id)

    async def get_store(
        self,
        session: AsyncSession,
        *,
        store_id: int,
    ) -> Optional[Dict[str, Any]]:
        rec = await session.execute(
            text(
                """
                SELECT id,
                       platform,
                       shop_id,
                       name,
                       active,
                       email,
                       contact_name,
                       contact_phone
                  FROM stores
                 WHERE id = :id
                 LIMIT 1
                """
            ),
            {"id": store_id},
        )
        row = rec.mappings().first()
        return dict(row) if row else None
