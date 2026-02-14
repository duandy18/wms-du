# app/services/test_shop_testset_guard_service.py
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.problem import make_problem
from app.services.fsku_components_repo import load_component_item_ids
from app.services.item_test_set_service import ItemTestSetService
from app.services.platform_test_shop_service import PlatformTestShopService


class TestShopTestSetGuardService:
    """
    宇宙边界（唯一真相：platform_test_shops + item_test_sets）：

    目标：测试商品（Test Set）不能进入任何“非测试商铺”，避免污染真实业务宇宙。

    规则（code=DEFAULT）：
    - 非 TEST shop：若 FSKU.components 命中 Test Set -> 409（禁止绑定/写入）
    - TEST shop：不强制 all-in Test Set（放行；是否 all-in 由 order-sim 等调试入口兜底）
    - FSKU 无 components：放行（合同兼容；后续解析会走 FSKU_NOT_EXECUTABLE）
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.ts = ItemTestSetService(session)
        self.test_shop = PlatformTestShopService(session)

    async def guard_fsku_components_by_shop(
        self,
        *,
        platform: str,
        shop_id: str,
        store_id: int | None,
        fsku_id: int,
        set_code: str = "DEFAULT",
        path: str,
        method: str,
    ) -> None:
        comp_item_ids = await load_component_item_ids(self.session, fsku_id=int(fsku_id))
        if not comp_item_ids:
            # ✅ 兼容合同：允许绑定“无 components”的 published FSKU
            return

        is_test = await self.test_shop.is_test_shop(platform=str(platform), shop_id=str(shop_id), code="DEFAULT")
        if is_test:
            # ✅ TEST shop 不强制 all-in；order-sim 等调试入口会做更严格兜底
            return

        # ✅ 非 TEST shop：禁止 Test Set items 进入
        try:
            await self.ts.assert_items_not_in_test_set(item_ids=comp_item_ids, set_code=set_code)
        except ItemTestSetService.NotFound as e:
            raise HTTPException(
                status_code=500,
                detail=make_problem(
                    status_code=500,
                    error_code="internal_error",
                    message=f"测试集合不可用：{e.message}",
                    context={
                        "path": path,
                        "method": method,
                        "platform": str(platform),
                        "store_id": int(store_id) if store_id is not None else None,
                        "shop_id": str(shop_id),
                        "set_code": str(set_code),
                        "fsku_id": int(fsku_id),
                    },
                ),
            )
        except ItemTestSetService.Conflict as e:
            # e.out_of_set_item_ids 这里代表“命中 Test Set 的 item_ids”（即禁止进入的测试商品）
            raise HTTPException(
                status_code=409,
                detail=make_problem(
                    status_code=409,
                    error_code="conflict",
                    message=e.message,
                    context={
                        "path": path,
                        "method": method,
                        "platform": str(platform),
                        "store_id": int(store_id) if store_id is not None else None,
                        "shop_id": str(shop_id),
                        "set_code": e.set_code,
                        "fsku_id": int(fsku_id),
                        "out_of_set_item_ids": e.out_of_set_item_ids,
                    },
                ),
            )
