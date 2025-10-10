from fastapi import FastAPI

from app.api.endpoints import api_router
from app.api.errors import BizError, biz_error_handler
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.scheduler import init_scheduler


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(level=settings.LOG_LEVEL)

    app = FastAPI(title="WMS-DU (local)")
    app.include_router(api_router)
    app.add_exception_handler(BizError, biz_error_handler)

    # ✅ 初始化快照定时任务（按环境变量 ENABLE_SNAPSHOT_SCHEDULER 控制）
    init_scheduler()

    return app


app = create_app()
