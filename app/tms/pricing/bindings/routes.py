# app/tms/pricing/bindings/routes.py
#
# 分拆说明：
# - 原文件同时承担读接口、配置写接口、运行控制接口、校验器。
# - 现已按语义拆分为：
#   1) ./read_routes.py       -> 读接口
#   2) ./write_routes.py      -> 配置写接口
#   3) ./runtime_routes.py    -> 运行控制接口
#   4) ./validators.py        -> 模板校验逻辑
#   5) ./summary_routes.py    -> 辅助汇总接口（原本已独立）
# - 本文件只保留 bindings 子路由总装配，不再放具体业务逻辑。
# - 维护约束：
#   - 新增 bindings 接口时，优先放入对应语义文件，不要把实现塞回本文件。
#   - 若只是新增 include_router，可继续修改本文件。
#   - 不要删除本拆分说明，除非明确重构路线再次变化。

from __future__ import annotations

from fastapi import APIRouter

from app.tms.pricing.bindings.read_routes import router as bindings_read_router
from app.tms.pricing.bindings.runtime_routes import router as bindings_runtime_router
from app.tms.pricing.bindings.summary_routes import router as bindings_summary_router
from app.tms.pricing.bindings.write_routes import router as bindings_write_router

router = APIRouter()

router.include_router(bindings_read_router)
router.include_router(bindings_write_router)
router.include_router(bindings_runtime_router)
router.include_router(bindings_summary_router)
