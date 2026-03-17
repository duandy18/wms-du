# app/tms/billing/router.py
#
# 分拆说明：
# - 本文件是 TMS / Billing 的路由壳。
# - 目标是承接快递公司对账单（shipping bills）导入、查询与对账入口。
# - 该域为新增域，不复用历史 app/api/routers 实现；
# - 当前阶段负责：外部账单原始证据入库、查询、对账回写。
from __future__ import annotations

from fastapi import APIRouter

from . import routes_import
from . import routes_items
from . import routes_reconcile
from . import routes_reconciliations

router = APIRouter(tags=["shipping-bills"])


def _register_all_routes() -> None:
    routes_import.register(router)
    routes_items.register(router)
    routes_reconcile.register(router)
    routes_reconciliations.register(router)


_register_all_routes()
