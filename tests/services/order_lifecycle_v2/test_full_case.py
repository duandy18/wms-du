# tests/services/order_lifecycle_v2/test_full_case.py
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_lifecycle_v2 import OrderLifecycleV2Service
from tests.services.order_lifecycle_v2.seeders import seed_full_lifecycle_case

pytestmark = pytest.mark.asyncio


async def test_order_lifecycle_v2_full_case(session: AsyncSession):
    trace_id = await seed_full_lifecycle_case(session)

    svc = OrderLifecycleV2Service(session)
    stages, summary = await svc.for_trace_id_with_summary(trace_id)

    keys = {s.key for s in stages if s.present}
    assert "created" in keys
    assert "outbound" in keys
    assert "shipped" in keys
    assert "returned" in keys

    assert summary.health in ("OK", "WARN")
    assert summary.health != "BAD"
