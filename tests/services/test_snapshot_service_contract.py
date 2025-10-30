import pytest

pytestmark = pytest.mark.grp_snapshot

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def test_snapshot_service_calls_proc_and_reads_views(session, monkeypatch):
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
