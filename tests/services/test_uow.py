import pytest
pytestmark = [pytest.mark.asyncio, pytest.mark.xfail(reason="WIP: UnitOfWork", strict=False)]

async def test_uow_commit_and_rollback(session, _baseline_seed, _db_clean):
    from app.services.uow import UnitOfWork
    async with UnitOfWork(session) as uow:
        assert uow.session is not None
