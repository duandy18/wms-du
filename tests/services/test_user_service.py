import pytest
pytestmark = [pytest.mark.asyncio, pytest.mark.xfail(reason="WIP: user CRUD", strict=False)]

async def test_user_crud(session, _baseline_seed, _db_clean):
    from app.services.user_service import UserService
    svc = UserService()
    uid = await svc.create_user(session=session, username="tester")
    got = await svc.get_user(session=session, user_id=uid)
    assert got is not None
