from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class StoreService:
    """
    店铺档案与仓库绑定服务。

    目前提供四个静态方法：

    - ensure_store:
        按 (platform, shop_id) UPSERT 店铺，返回 store_id。

    - bind_warehouse:
        绑定店铺与仓库（支持 is_default / is_top / priority），
        保证每个店铺最多只有一个“主仓”（is_top = true）。

    - resolve_default_warehouse:
        按 store_id 解析“默认仓”（优先主仓，再看 is_default，再看 priority）。

    - resolve_default_warehouse_for_platform_shop:
        按 (platform, shop_id) 解析默认仓（内部会自动 ensure_store）。
    """

    # ------------------------------------------------------------------
    # 店铺 UPSERT
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

        参数：
        - store_id     : 店铺 ID
        - warehouse_id : 仓库 ID
        - is_default   : 是否“默认仓”（历史字段，仍然保留）
        - priority     : 路由优先级，数字越小越靠前
        - is_top       : 是否“主仓”；若为 None，则默认等同于 is_default

        规则（C.1 收口）：
        - is_top 为 True 时，保证同一 store 仅有一个 is_top = True：
            先把该 store 所有记录 is_top 置为 False，再 upsert 当前记录为 True。
        - is_default 为 True 时，同时复用 is_top 语义（即默认同时是主仓）；
        - 老数据场景：
            若历史上只有 is_default，没有 is_top，仍能正常工作：
            - 本方法第一次被调用时会把这条记录的 is_top 设置为 True。
        """
        if is_top is None:
            # 默认策略：跟随 is_default
            is_top = is_default

        # 若要设置主仓 / 默认仓，先清空同店其他记录的 is_top
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

        排序规则（C.1 定稿）：
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
