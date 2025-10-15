# app/main.py
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

    # ✅（可选）安装慢 SQL 监听；若相关模块不存在，会自动跳过，不影响运行
    try:
        from app.db.session import async_engine  # 假设项目使用 AsyncEngine
        from app.infra.sql_tap import install as install_sql_tap

        install_sql_tap(async_engine.sync_engine)
    except Exception:
        # 静默跳过，避免对现有部署产生硬依赖
        pass

    return app


app = create_app()
