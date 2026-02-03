# tests/services/order_lifecycle_v2/test_missing_shipped.py
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_lifecycle_v2 import OrderLifecycleV2Service
from tests.services.order_lifecycle_v2.seeders import seed_missing_shipped_case

pytestmark = pytest.mark.asyncio


async def test_order_lifecycle_v2_missing_shipped(session: AsyncSession):
    trace_id = await seed_missing_shipped_case(session)

    svc = OrderLifecycleV2Service(session)
    stages, summary = await svc.for_trace_id_with_summary(trace_id)

    keys = {s.key for s in stages if s.present}
    assert "outbound" in keys
    assert "shipped" not in keys

    assert summary.health in ("WARN", "BAD")
    joined = "\n".join(summary.issues)
    assert "发运" in joined or "发货" in joined or "ship" in joined.lower()
