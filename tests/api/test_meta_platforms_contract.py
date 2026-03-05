# tests/api/test_meta_platforms_contract.py
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_meta_platforms_contract_shape():
    client = TestClient(app)

    # 这里不假设一定有数据（种子库可能为空），只锁定形状
    r = client.get("/meta/platforms")
    assert r.status_code in (200, 401, 403)

    # 如果项目需要登录，401/403 也算“合同符合安全预期”
    if r.status_code != 200:
        return

    j = r.json()
    assert isinstance(j, dict)
    assert j.get("ok") is True
    assert isinstance(j.get("data"), list)

    for it in j["data"]:
        assert isinstance(it, dict)
        assert isinstance(it.get("platform"), str) and it["platform"].strip()
        assert isinstance(it.get("label"), str) and it["label"].strip()
        assert isinstance(it.get("enabled"), bool)
        # 输出应统一大写（事实出口统一）
        assert it["platform"] == it["platform"].upper()
