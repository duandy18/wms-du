# app/tms/shipment/router.py
#
# 分拆说明：
# - 本文件是 TMS / Shipment 的路由壳。
# - Phase-2 终态下，Shipment 创建入口已统一收口到 orders_v2 ship-with-waybill；
# - 历史 /ship/confirm 路径已废弃并删除；
# - 当前保留本壳文件，作为后续 Shipment 直达入口扩展点。
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["ship"])
