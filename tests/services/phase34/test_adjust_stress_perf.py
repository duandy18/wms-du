# pytest: new file
# Path: tests/services/phase34/test_adjust_stress_perf.py
import asyncio
import statistics
import time
from datetime import datetime

import pytest

pytestmark = pytest.mark.grp_phase34

# 允许在 CI 上快速跑；本地可放大并发规模
CONCURRENCY = int(pytest.config.getoption("--p34c") if hasattr(pytest, "config") else 32)
ROUNDS = int(pytest.config.getoption("--p34n") if hasattr(pytest, "config") else 3)


async def _seed(async_session, qty):
    await async_session.execute(
        """
        DELETE FROM stocks WHERE item_id=3003 AND warehouse_id=1 AND location_id=900 AND batch_code='NEAR';
        INSERT INTO stocks (item_id, warehouse_id, location_id, batch_code, qty)
        VALUES (3003, 1, 900, 'NEAR', :qty);
    """,
        {"qty": qty},
    )
    await async_session.commit()


async def _probe_adjust(async_client):
    # 用 /scan/count/commit 做“调账代理”若无专门 adjust API。
    # 你有 StockService.adjust，但 HTTP 层可能没有暴露；这里走 scan/count 也能压锁粒度。
    try:
        r = await async_client.post("/scan/count/commit", json={})
        return r.status_code in (200, 400, 401, 403, 404, 405, 422)
    except Exception:
        return False


def _build_count_payload(delta):
    # 通过 COUNT 让系统将目标批次修正为 “当前+delta” 的方式实现批量并发写入
    # 若你的 COUNT 语义是“绝对盘点”，可以先读再写目标数值；为便于压力测试，这里直接给出调整为非负值的随机目标
    return {
        "warehouse_id": 1,
        "lines": [
            {
                "item_id": 3003,
                "batch_code": "NEAR",
                "target_delta": delta,
                "ref": f"P34-ADJ-{int(time.time() * 1000)}",
            }
        ],
        "ts": datetime.utcnow().isoformat(),
    }


@pytest.mark.asyncio
async def test_adjust_concurrency_perf(async_client, async_session):
    if not await _probe_adjust(async_client):
        pytest.skip("No adjust-like endpoint (using /scan/count/commit as proxy); skip perf test")

    await _seed(async_session, qty=10)

    latencies = []
    for _ in range(ROUNDS):
        # 构造同一批次小幅度震荡的并发调账（正负交错）
        deltas = [1 if i % 2 == 0 else -1 for i in range(CONCURRENCY)]

        async def _hit(d):
            t0 = time.perf_counter()
            r = await async_client.post("/scan/count/commit", json=_build_count_payload(d))
            t1 = time.perf_counter()
            return (r.status_code, (t1 - t0) * 1000)

        results = await asyncio.gather(*[_hit(d) for d in deltas])
        latencies.extend([ms for _, ms in results])
        # 允许系统写落账后短暂歇息
        await asyncio.sleep(0.1)

    # 统计
    p50 = statistics.median(latencies)
    p95 = sorted(latencies)[int(len(latencies) * 0.95) - 1]
    p99 = sorted(latencies)[max(int(len(latencies) * 0.99) - 1, 0)]

    # 给出一个保守红线（CI 可放宽，本地可收紧）
    assert p99 < 1500, f"p99 too high: {p99:.1f} ms (p95={p95:.1f}, p50={p50:.1f})"
