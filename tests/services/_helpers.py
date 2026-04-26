from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def uniq_ref(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


async def ensure_store(
    session: AsyncSession,
    platform: str = "__internal__",
    store_code: str = "__internal__",  # 新增：显式 store_code
    name: str = "__NO_STORE__",
) -> int:
    """
    创建或确保一个内部测试店铺存在。

    说明：
    - stores.store_code 现在是 NOT NULL，并且 (platform, store_code) 上有唯一约束；
    - 老版本只插 platform + name，会触发 NOT NULL 约束；
    - 因此这里必须明确写入 store_code，并使用 (platform, store_code) 作为主幂等键。
    """

    # 1) 插入（如存在则忽略）
    await session.execute(
        text(
            """
            INSERT INTO stores (
  platform,
  store_code,
  store_name
)
VALUES (
  :p,
  :sid,
  :n
)
            ON CONFLICT (platform, store_code) DO NOTHING
            """
        ),
        {
            "p": platform,
            "sid": store_code,
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
               AND store_code = :sid2
             ORDER BY id
             LIMIT 1
            """
        ),
        {
            "p2": platform,
            "sid2": store_code,
        },
    )
    return int(row.scalar_one())
