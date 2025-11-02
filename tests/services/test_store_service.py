import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.xfail(reason="WIP: store CRUD", strict=False)]

async def test_store_crud_and_visibility(session, _baseline_seed, _db_clean):
    from app.services.store_service import StoreService
    svc = StoreService()
    sid = await svc.create_store(session=session, name="测试门店", code="S001")
    got = await svc.get_store(session=session, store_id=sid)
    assert got is not None
