# tests/services/test_store_service.py
import uuid

import pytest

pytestmark = [pytest.mark.asyncio]


async def test_store_crud_and_visibility(session, _db_clean_and_seed):
    """
    最小契约：

    - 能通过 StoreService.create_store() 创建一条 stores 记录；
    - 能通过 StoreService.get_store() 读回该记录（非 None 即可）。

    注意：
    - 使用随机 code / shop_id，避免与基线种子中的店铺唯一键冲突。
    """
    from app.services.store_service import StoreService

    svc = StoreService()

    suffix = uuid.uuid4().hex[:8]
    name = f"测试门店-{suffix}"
    code = f"S-{suffix}"

    # 创建一个基础店铺（platform / shop_id 使用内部默认）
    store_id = await svc.create_store(
        session=session,
        name=name,
        code=code,
    )

    assert isinstance(store_id, int)
    assert store_id > 0

    # 读回店铺信息
    got = await svc.get_store(session=session, store_id=store_id)
    assert got is not None
    assert got["id"] == store_id
    assert got["name"] == name
