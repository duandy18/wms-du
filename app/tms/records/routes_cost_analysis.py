# app/tms/records/routes_cost_analysis.py
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.tms.records.contracts import (
    RecordsCostAnalysisByCarrierRowOut,
    RecordsCostAnalysisByTimeRowOut,
    RecordsCostAnalysisResponse,
    RecordsCostAnalysisSummaryOut,
)
from app.tms.records.repository_cost_analysis import get_records_cost_analysis


def _parse_date_param(value: str | None) -> date | None:
    v = (value or "").strip()
    if not v:
        return None
    return date.fromisoformat(v)


def register(router: APIRouter) -> None:
    @router.get(
        "/cost-analysis",
        response_model=RecordsCostAnalysisResponse,
        summary="物流台帐预估成本分析",
    )
    async def get_records_cost_analysis_route(
        carrier_code: str | None = Query(None),
        start_date: str | None = Query(None),
        end_date: str | None = Query(None),
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
    ) -> RecordsCostAnalysisResponse:
        del current_user

        start_date_parsed = _parse_date_param(start_date)
        end_date_parsed = _parse_date_param(end_date)

        if (
            start_date_parsed is not None
            and end_date_parsed is not None
            and start_date_parsed > end_date_parsed
        ):
            raise HTTPException(status_code=400, detail="start_date cannot be after end_date")

        data = await get_records_cost_analysis(
            session=session,
            carrier_code=carrier_code,
            start_date=start_date_parsed,
            end_date=end_date_parsed,
        )

        return RecordsCostAnalysisResponse(
            ok=True,
            summary=RecordsCostAnalysisSummaryOut(**dict(data["summary"])),
            by_carrier=[
                RecordsCostAnalysisByCarrierRowOut(**row)
                for row in list(data["by_carrier"])
            ],
            by_time=[
                RecordsCostAnalysisByTimeRowOut(**row)
                for row in list(data["by_time"])
            ],
        )
