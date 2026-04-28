from fastapi import APIRouter


router = APIRouter()

# Collector 分离后，OMS 不再保留旧平台采集事实桥接。
# 后续 Collector -> OMS 导入合同落地后，再在本模块挂接新的平台订单镜像 / 履约订单转化路由。
