# tests/api/test_dev_fake_orders_generate_run_contract.py
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def _seed_minimal() -> dict:
    return {
        "platform": "PDD",
        "shops": [
            {
                "shop_id": "1",
                "title_prefix": "【模拟】",
                "links": [
                    {
                        "spu_key": "SPU-1",
                        "title": "测试商品",
                        "variants": [{"variant_name": "默认规格", "filled_code": "UT-REPLAY-FSKU-1"}],
                    }
                ],
            }
        ],
    }


def test_generate_returns_orders_and_batch_id(monkeypatch) -> None:
    monkeypatch.setenv("WMS_ENV", "dev")
    c = TestClient(app)

    r = c.post("/dev/fake-orders/generate", json={"seed": _seed_minimal(), "generate": {"count": 3}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["batch_id"]
    assert len(body["orders"]) == 3
    assert "gen_stats" in body


def test_run_returns_report_shape(monkeypatch) -> None:
    monkeypatch.setenv("WMS_ENV", "dev")
    c = TestClient(app)

    r = c.post(
        "/dev/fake-orders/run",
        json={
            "seed": _seed_minimal(),
            "generate": {"count": 1, "lines_min": 1, "lines_max": 1, "qty_min": 1, "qty_max": 1, "rng_seed": 42},
            "with_replay": True,
            "watch_filled_codes": ["UT-REPLAY-FSKU-1"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # 解析模拟的核心：report + gen_stats（其余字段就算存在也不强依赖）
    assert "report" in body and isinstance(body["report"], dict)
    assert "gen_stats" in body and isinstance(body["gen_stats"], dict)

    report = body["report"]
    assert "by_status" in report
    assert "watch_stats" in report
    assert "expanded_items_multiplication" in report
    assert "replay_stats" in report
