# app/api/routers/pricing_integrity/router.py
from __future__ import annotations

from fastapi import APIRouter

from . import active_schemes, cleanup

router = APIRouter(tags=["ops - pricing-integrity"])

# 终态：
# - zone / bracket / archive-release / one-click 等旧运维动作已移除
# - 仅保留：
#   1) active_schemes：辅助运维挑选方案
#   2) cleanup：清理空壳/无效 pricing schemes
active_schemes.register(router)
cleanup.register(router)
