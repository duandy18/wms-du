import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.putaway_service import PutawayService, SameLocationError

pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_putaway_same_location_error(session: AsyncSession):
    svc = PutawayService()
    with pytest.raises(SameLocationError):
        async with session.begin():
            await svc.putaway(
                session=session,
                item_id=606,
                from_location_id=1,
                to_location_id=1,  # same
                qty=1,
                ref="PUT-SAME-LOC-1",
            )
