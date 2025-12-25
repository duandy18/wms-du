# app/api/routers/scan_routes_putaway_disabled.py
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.routers.scan_schemas import ScanPutawayCommitRequest, ScanResponse


def register(router: APIRouter) -> None:
    # ==========================
    # /scan/putaway/commit（LEGACY：已禁用）
    # ==========================

    @router.post(
        "/scan/putaway/commit", response_model=ScanResponse, status_code=status.HTTP_200_OK
    )
    async def scan_putaway_commit(
        req: ScanPutawayCommitRequest,  # noqa: ARG001
        session: AsyncSession = Depends(get_session),  # noqa: ARG001
    ) -> ScanResponse:
        """
        业务上 scan 通路已无 location 概念，putaway 功能在扫描通路中禁用。
        保留该路由仅为兼容历史调用，统一返回 FEATURE_DISABLED。
        """
        return ScanResponse(
            ok=False,
            committed=False,
            scan_ref="",
            event_id=None,
            source="scan_putaway_disabled",
            errors=[
                {
                    "stage": "putaway",
                    "error": "FEATURE_DISABLED: putaway is not supported on /scan without locations",
                }
            ],
        )
