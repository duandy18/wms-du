# app/api/routers/dev_fake_orders_routes.py
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.problem import make_problem

from app.api.routers.dev_fake_orders_guard import dev_only_guard
from app.api.routers.dev_fake_orders_ingest import run_single_ingest
from app.api.routers.dev_fake_orders_replay import run_single_replay
from app.api.routers.dev_fake_orders_schemas import (
    DevFakeOrdersGenerateIn,
    DevFakeOrdersGenerateOut,
    DevFakeOrdersRunIn,
    DevFakeOrdersRunOut,
)

from app.services.devtools.fake_orders_service import build_report, generate_orders, parse_seed

router = APIRouter(prefix="/dev/fake-orders", tags=["devtools", "fake-orders"])


def _derive_watch_from_gen_stats(gen_stats: Dict[str, Any]) -> List[str]:
    vu = gen_stats.get("variants_used") or {}
    if isinstance(vu, dict):
        return [str(k) for k in vu.keys() if k][:6]
    return []


async def _run_orders(
    session: AsyncSession,
    *,
    orders: List[Dict[str, Any]],
    with_replay: bool,
    dev_batch_id: str,
) -> Tuple[List[Dict[str, Any]], Optional[List[Dict[str, Any]]]]:
    ingest_resps: List[Dict[str, Any]] = []
    replay_resps: Optional[List[Dict[str, Any]]] = [] if with_replay else None

    for o in orders:
        ing = await run_single_ingest(session, o, dev_batch_id=dev_batch_id)
        ingest_resps.append(ing)

        if with_replay:
            rp = await run_single_replay(
                session,
                platform=str(o.get("platform")),
                store_id=int(ing.get("store_id")),
                ext_order_no=str(o.get("ext_order_no")),
            )
            replay_resps.append(rp)

    return ingest_resps, replay_resps


@router.post("/generate", response_model=DevFakeOrdersGenerateOut)
async def generate_fake_orders(
    payload: DevFakeOrdersGenerateIn,
    _guard: None = Depends(dev_only_guard),
) -> DevFakeOrdersGenerateOut:
    try:
        seed = parse_seed(payload.seed)
        orders, gen_stats = generate_orders(
            seed=seed,
            count=payload.generate.count,
            lines_min=payload.generate.lines_min,
            lines_max=payload.generate.lines_max,
            qty_min=payload.generate.qty_min,
            qty_max=payload.generate.qty_max,
            rng_seed=payload.generate.rng_seed,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=make_problem(
                status_code=422,
                error_code="request_validation_error",
                message=str(e),
                context={"path": "/dev/fake-orders/generate", "method": "POST"},
            ),
        )

    batch_id = f"DEVFAKE-{uuid.uuid4().hex[:12]}"
    return DevFakeOrdersGenerateOut(batch_id=batch_id, orders=orders, gen_stats=gen_stats)


@router.post("/run", response_model=DevFakeOrdersRunOut)
async def run_fake_orders(
    payload: DevFakeOrdersRunIn,
    _guard: None = Depends(dev_only_guard),
    session: AsyncSession = Depends(get_session),
) -> DevFakeOrdersRunOut:
    # 解析模拟：核心输出 report + gen_stats
    try:
        seed = parse_seed(payload.seed)
        orders, gen_stats = generate_orders(
            seed=seed,
            count=payload.generate.count,
            lines_min=payload.generate.lines_min,
            lines_max=payload.generate.lines_max,
            qty_min=payload.generate.qty_min,
            qty_max=payload.generate.qty_max,
            rng_seed=payload.generate.rng_seed,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=make_problem(
                status_code=422,
                error_code="request_validation_error",
                message=str(e),
                context={"path": "/dev/fake-orders/run", "method": "POST"},
            ),
        )

    dev_batch_id = f"DEVFAKE-{uuid.uuid4().hex[:12]}"
    watch = payload.watch_filled_codes or _derive_watch_from_gen_stats(gen_stats)

    ingest_resps, replay_resps = await _run_orders(
        session,
        orders=orders,
        with_replay=payload.with_replay,
        dev_batch_id=dev_batch_id,
    )

    report = build_report(
        orders=orders,
        ingest_responses=ingest_resps,
        watch_filled_codes=watch,
        replay_responses=replay_resps,
    )

    return DevFakeOrdersRunOut(report=report, gen_stats=gen_stats)
