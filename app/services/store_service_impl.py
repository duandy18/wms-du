# app/services/store_service_impl.py
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class StoreService:
    """
    店铺档案与仓库绑定服务 + 最小 CRUD（实现体）。

    现阶段提供两类能力：

    1）店铺 + 仓库路由相关（已在 Phase 3.x 使用）：
        - ensure_store
        - bind_warehouse
        - resolve_default_warehouse
        - resolve_default_warehouse_for_platform_shop

    2）最小 CRUD（供 tests/services/test_store_service.py 使用）：
        - create_store(session, name, code, platform="INTERNAL", shop_id=None)
        - get_store(session, store_id)
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
        """
        按 (platform, shop_id) UPSERT 店铺，返回 store_id。

        约定：
        - platform 一律大写存储；
        - name 允许为空，若未指定，则使用 "{PLAT}-{shop_id}"。
        """
        plat = platform.upper()

        # 先查是否已存在
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

        # UPSERT（有 uq_stores_platform_shop 保护）
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

        表结构（参考模型）：
        - 表：store_warehouse
        - 字段：
            id           BIGINT PK
            store_id     INT  NOT NULL
            warehouse_id INT  NOT NULL
            is_top       BOOL NOT NULL DEFAULT FALSE
            is_default   BOOL NOT NULL DEFAULT FALSE
            priority     INT  NOT NULL DEFAULT 100
        """
        if is_top is None:
            # 默认策略：跟随 is_default
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

        # 幂等 UPSERT 当前绑定
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
    # 默认仓解析
    # ------------------------------------------------------------------
    @staticmethod
    async def resolve_default_warehouse(
        session: AsyncSession,
        *,
        store_id: int,
    ) -> Optional[int]:
        """
        解析“默认仓”（可用于路由/默认选仓）。

        排序规则：
        1. 优先 is_top = TRUE 的记录（主仓）
        2. 其次 is_default = TRUE 的记录
        3. 再按 priority 升序
        4. 再按 warehouse_id 升序

        返回：
        - 若存在记录：返回 warehouse_id
        - 若不存在：返回 None
        """
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
        """
        按 (platform, shop_id) 解析默认仓。

        行为：
        - 若店铺不存在：
            自动 ensure_store（不 commit，由调用方控制事务），然后无绑定则返回 None。
        - 若有 store_warehouse 绑定：
            走 resolve_default_warehouse 的排序逻辑。
        - 若无绑定：
            返回 None，由调用方决定是否兜底到某个仓。
        """
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
        """
        创建一个基础店铺记录，返回 store_id。

        说明：
        - Store 模型当前字段：
            platform (NOT NULL)
            shop_id  (NOT NULL)
            name     (NOT NULL, 默认 'NO-STORE')
            active   (NOT NULL, default TRUE)
            email / contact_name / contact_phone / timestamps 等可空或有默认值
        - 这里只写入 platform / shop_id / name，其他走默认值。
        - code 目前只作为测试入参，不写入 DB。
        """
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
        """
        按 ID 查询店铺。

        当前测试只要求 “返回非 None”，但这里返回一个 dict，便于以后演进为 DTO。
        """
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
