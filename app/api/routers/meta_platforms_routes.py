# app/api/routers/meta_platforms_routes.py
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_session
from app.db.deps import get_db


class MetaPlatformItem(BaseModel):
    platform: str = Field(..., min_length=1, max_length=32)
    label: str = Field(..., min_length=1, max_length=64)
    enabled: bool = True


class MetaPlatformsOut(BaseModel):
    ok: bool = True
    data: List[MetaPlatformItem]


def _label_for(platform: str) -> str:
    # 先给常见平台一个人类可读 label；未知平台就用自身
    m = {
        "PDD": "拼多多",
        "TB": "淘宝",
        "TMALL": "天猫",
        "JD": "京东",
        "DEMO": "DEMO",
        "OTHER": "其它",
    }
    return m.get(platform, platform)


def register(router: APIRouter) -> None:
    @router.get("/platforms", response_model=MetaPlatformsOut)
    async def list_platforms(
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        平台枚举（事实源：stores distinct）。
        - 前端只消费，不维护隐式常量
        - 输出统一大写
        - 当前不做 enabled/disabled 配置开关，默认 enabled=true
        """
        # 权限：沿用 stores 读权限（避免 meta 成为旁路）
        from app.api.routers import stores as stores_router

        stores_router._check_perm(db, current_user, ["config.store.read"])

        sql = text(
            """
            SELECT DISTINCT upper(s.platform) AS platform
              FROM stores AS s
             WHERE COALESCE(s.platform, '') <> ''
             ORDER BY upper(s.platform)
            """
        )
        rows = (await session.execute(sql)).mappings().all()

        items: list[MetaPlatformItem] = []
        for r in rows:
            plat = str(r.get("platform") or "").strip().upper()
            if not plat:
                continue
            items.append(MetaPlatformItem(platform=plat, label=_label_for(plat), enabled=True))

        return MetaPlatformsOut(ok=True, data=items)
