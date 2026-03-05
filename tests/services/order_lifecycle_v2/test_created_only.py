# tests/services/order_lifecycle_v2/test_created_only.py
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_lifecycle_v2 import OrderLifecycleV2Service
from tests.services.order_lifecycle_v2.seeders import seed_created_only_case

pytestmark = pytest.mark.asyncio


async def test_order_lifecycle_v2_created_only(session: AsyncSession):
    trace_id = await seed_created_only_case(session)

    svc = OrderLifecycleV2Service(session)
    stages, summary = await svc.for_trace_id_with_summary(trace_id)

    present_keys = {s.key for s in stages if s.present}
    assert "created" in present_keys
    assert "outbound" not in present_keys
    assert "shipped" not in present_keys
    assert "returned" not in present_keys

    assert summary.health in ("WARN", "BAD")
