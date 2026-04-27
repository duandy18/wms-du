# Module split: platform order ingestion pull-job executor registry.
#
# This is not a cross-platform business adapter. It only dispatches the common
# pull-job runner to platform-owned executor implementations.
from __future__ import annotations

from app.platform_order_ingestion.jd.pull_job_executor import JdPullJobExecutor
from app.platform_order_ingestion.pdd.pull_job_executor import PddPullJobExecutor
from app.platform_order_ingestion.taobao.pull_job_executor import TaobaoPullJobExecutor
from app.platform_order_ingestion.services.pull_job_executor import PlatformOrderPullJobExecutor


_EXECUTORS: dict[str, PlatformOrderPullJobExecutor] = {
    "pdd": PddPullJobExecutor(),
    "jd": JdPullJobExecutor(),
    "taobao": TaobaoPullJobExecutor(),
}


def get_pull_job_executor(platform: str) -> PlatformOrderPullJobExecutor | None:
    return _EXECUTORS.get(str(platform or "").strip().lower())
