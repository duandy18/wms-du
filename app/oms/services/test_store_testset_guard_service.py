# app/oms/services/test_store_testset_guard_service.py
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class TestShopTestSetGuardService:
    """
    商品集合隔离机制已退役。

    保留类名和方法签名，兼容现有调用方；
    不再按 FSKU components 做商品集合阻断。
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def guard_fsku_components_by_store(
        self,
        *,
        platform: str,
        store_code: str,
        store_id: int | None,
        fsku_id: int,
        set_code: str = "DEFAULT",
        path: str,
        method: str,
    ) -> None:
        return None
