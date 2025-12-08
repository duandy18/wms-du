# tests/services/test_user_service.py
import uuid

import pytest

pytestmark = [pytest.mark.asyncio]


async def test_user_crud(session, _db_clean_and_seed):
    """
    最小契约（异步版用户服务）：

    - 通过 AsyncUserService.create_user() 能插入一条 users 记录；
    - 通过 AsyncUserService.get_user() 能读回该记录（非 None 即可）。

    注意：
    - 使用随机 username，避免与基线种子中的用户唯一键冲突。
    """
    from app.services.user_service import AsyncUserService

    svc = AsyncUserService()

    username = f"tester_{uuid.uuid4().hex[:8]}"

    user_id = await svc.create_user(
        session=session,
        username=username,
    )

    assert isinstance(user_id, int)
    assert user_id > 0

    got = await svc.get_user(session=session, user_id=user_id)
    assert got is not None
    assert got["id"] == user_id
    assert got["username"] == username
