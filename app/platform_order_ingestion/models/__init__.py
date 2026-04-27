# app/platform_order_ingestion/models/__init__.py
# Domain-owned ORM models for OMS platform access and platform order facts.

from app.platform_order_ingestion.models.jd_app_config import JdAppConfig
from app.platform_order_ingestion.models.jd_order import JdOrder, JdOrderItem
from app.platform_order_ingestion.models.pdd_app_config import PddAppConfig
from app.platform_order_ingestion.models.pdd_order import PddOrder, PddOrderItem
from app.platform_order_ingestion.models.pdd_order_order_mapping import PddOrderOrderMapping
from app.platform_order_ingestion.models.pull_job import PlatformOrderPullJob, PlatformOrderPullJobRun, PlatformOrderPullJobRunLog
from app.platform_order_ingestion.models.store_platform_connection import StorePlatformConnection
from app.platform_order_ingestion.models.store_platform_credential import StorePlatformCredential
from app.platform_order_ingestion.models.store_token import StoreToken
from app.platform_order_ingestion.models.taobao_app_config import TaobaoAppConfig
from app.platform_order_ingestion.models.taobao_order import TaobaoOrder, TaobaoOrderItem

__all__ = [
    "JdAppConfig",
    "JdOrder",
    "JdOrderItem",
    "PddAppConfig",
    "PddOrder",
    "PddOrderItem",
    "PddOrderOrderMapping",
    "PlatformOrderPullJobRunLog",
    "PlatformOrderPullJobRun",
    "PlatformOrderPullJob",
    "StorePlatformConnection",
    "StorePlatformCredential",
    "StoreToken",
    "TaobaoAppConfig",
    "TaobaoOrder",
    "TaobaoOrderItem",
]
