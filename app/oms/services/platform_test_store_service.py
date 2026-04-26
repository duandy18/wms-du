# app/oms/services/platform_test_store_service.py
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class PlatformTestStoreService:
    """
    测试店铺入口判定（唯一真相：platform_test_stores）。

    终态口径：
    - store_id：内部店铺主键 stores.id
    - store_code：平台店铺编码 / 平台店铺号
    - code='DEFAULT'：默认测试店铺集合
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def is_test_store(
        self,
        *,
        store_id: int | None = None,
        platform: str | None = None,
        store_code: str | None = None,
        code: str = "DEFAULT",
    ) -> bool:
        if store_id is not None:
            row = (
                await self.session.execute(
                    text(
                        """
                        SELECT 1
                          FROM platform_test_stores
                         WHERE store_id = :store_id
                           AND code = :code
                         LIMIT 1
                        """
                    ),
                    {"store_id": int(store_id), "code": str(code)},
                )
            ).first()
            return row is not None

        if platform is not None and store_code is not None:
            row = (
                await self.session.execute(
                    text(
                        """
                        SELECT 1
                          FROM platform_test_stores
                         WHERE platform = :p
                           AND store_code = :store_code
                           AND code = :code
                         LIMIT 1
                        """
                    ),
                    {
                        "p": str(platform).upper(),
                        "store_code": str(store_code),
                        "code": str(code),
                    },
                )
            ).first()
            return row is not None

        raise TypeError("is_test_store requires either store_id or platform + store_code")
