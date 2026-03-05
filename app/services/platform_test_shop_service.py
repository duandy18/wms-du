# app/services/platform_test_shop_service.py
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class PlatformTestShopService:
    """
    测试商铺入口判定（唯一真相：platform_test_shops）。

    - 不再靠环境变量/硬编码
    - 默认只看 code='DEFAULT'
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def is_test_shop(self, *, platform: str, shop_id: str, code: str = "DEFAULT") -> bool:
        row = (
            await self.session.execute(
                text(
                    """
                    SELECT 1
                      FROM platform_test_shops
                     WHERE platform = :p
                       AND shop_id = :sid
                       AND code = :code
                     LIMIT 1
                    """
                ),
                {"p": str(platform), "sid": str(shop_id), "code": str(code)},
            )
        ).first()
        return row is not None

    async def is_test_store(self, *, store_id: int, code: str = "DEFAULT") -> bool:
        row = (
            await self.session.execute(
                text(
                    """
                    SELECT 1
                      FROM platform_test_shops
                     WHERE store_id = :store_id
                       AND code = :code
                     LIMIT 1
                    """
                ),
                {"store_id": int(store_id), "code": str(code)},
            )
        ).first()
        return row is not None
