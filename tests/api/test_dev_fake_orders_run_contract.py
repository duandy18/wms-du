# tests/api/test_dev_fake_orders_run_contract.py
from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.main import app


def test_dev_fake_orders_run_seed_validation_returns_422_not_500(monkeypatch) -> None:
    # 确保 dev guard 不把我们挡在门外
    monkeypatch.setenv("WMS_ENV", "dev")

    c = TestClient(app)

    # 关键：seed 缺 shops -> parse_seed 抛 ValueError
    # 正确行为：422 request_validation_error（而不是 500 internal_error）
    r = c.post("/dev/fake-orders/run", json={"seed": {}})
    assert r.status_code == 422, r.text

    body = r.json()
    assert body.get("error_code") == "request_validation_error", body
    assert "Seed" in (body.get("message") or "") or "seed" in (body.get("message") or "") or body.get("message"), body


def test_dev_fake_orders_run_response_shape(monkeypatch) -> None:
    monkeypatch.setenv("WMS_ENV", "dev")

    c = TestClient(app)

    # 注意：这里不强行要求“业务全绿”，只验证“结构完整+接口稳定”
    payload = {
        "seed": {
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
        },
        "with_replay": True,
        "watch_filled_codes": ["UT-REPLAY-FSKU-1"],
        "generate": {"count": 2, "lines_min": 1, "lines_max": 1, "qty_min": 1, "qty_max": 1, "rng_seed": 42},
    }

    r = c.post("/dev/fake-orders/run", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()

    assert "report" in body and isinstance(body["report"], dict)
    assert "gen_stats" in body and isinstance(body["gen_stats"], dict)

    report = body["report"]
    assert "by_status" in report
    assert "by_unresolved_reason" in report
    assert "watch_stats" in report
    assert "expanded_items_multiplication" in report
    assert "replay_stats" in report
