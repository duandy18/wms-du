from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def uniq_ref(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


async def ensure_store(
    session: AsyncSession,
    platform: str = "__internal__",
    shop_id: str = "__internal__",  # 新增：显式 shop_id
    name: str = "__NO_STORE__",
) -> int:
    """
    创建或确保一个内部测试店铺存在。

    说明：
    - stores.shop_id 现在是 NOT NULL，并且 (platform, shop_id) 上有唯一约束；
    - 老版本只插 platform + name，会触发 NOT NULL 约束；
    - 因此这里必须明确写入 shop_id，并使用 (platform, shop_id) 作为主幂等键。
    """

    # 1) 插入（如存在则忽略）
    await session.execute(
        text(
            """
            INSERT INTO stores(platform, shop_id, name)
            VALUES (:p, :sid, :n)
            ON CONFLICT (platform, shop_id) DO NOTHING
            """
        ),
        {
            "p": platform,
            "sid": shop_id,
            "n": name,
        },
    )

    # 2) 返回对应 store_id
    row = await session.execute(
        text(
            """
            SELECT id
              FROM stores
             WHERE platform = :p2
               AND shop_id = :sid2
             ORDER BY id
             LIMIT 1
            """
        ),
        {
            "p2": platform,
            "sid2": shop_id,
        },
    )
    return int(row.scalar_one())
