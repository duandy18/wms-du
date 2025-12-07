# tests/services/test_snapshot_service_contract.py
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_snapshot_service_calls_proc_and_reads_views(session, monkeypatch):
    """
    合同测试：

    - SnapshotService.run(session) 应该尝试执行：
        * CALL snapshot_today()
        * SELECT * FROM v_three_books
      （本测试通过 FakeSession 拦截 SQL 文本）

    - run() 返回值应包含 "sum_stocks" 等字段。
    """
    from app.services.snapshot_service import SnapshotService

    called = {"proc": False, "views": False}

    async def fake_exec(sql, *args, **kwargs):
        s = str(sql).strip().lower()
        if "call snapshot_today" in s:
            called["proc"] = True

            class R:
                pass

            return R()
        if "select * from v_three_books" in s:
            called["views"] = True

            class Row:
                def mappings(self):
                    return type(
                        "M",
                        (),
                        {
                            "first": lambda _self: {
                                "sum_stocks": 0,
                                "sum_ledger": 0,
                                "sum_snapshot_on_hand": 0,
                                "sum_snapshot_available": 0,
                            }
                        },
                    )()

            return Row()
        raise AssertionError("unexpected SQL: " + s)

    # monkeypatch session.execute
    class FakeSession:
        async def execute(self, sql, *a, **k):
            return await fake_exec(sql)

    svc = SnapshotService()
    res = await svc.run(FakeSession())  # 不依赖真实 DB
    assert called["proc"] and called["views"]
    assert "sum_stocks" in res
