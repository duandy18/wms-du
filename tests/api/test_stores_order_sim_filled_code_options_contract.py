# tests/api/test_stores_order_sim_filled_code_options_contract.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app


def _login_and_get_token(client: TestClient) -> str:
    resp = client.post(
        "/users/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data, dict)
    token = data.get("access_token")
    assert isinstance(token, str) and token.strip(), f"bad token payload: {data}"
    return token


def _auth_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _try_get_options(client: TestClient, *, token: str, store_id: int) -> Tuple[int, Dict[str, Any]]:
    resp = client.get(
        f"/stores/{store_id}/order-sim/filled-code-options",
        headers=_auth_headers(token),
    )
    try:
        payload = resp.json()
    except Exception:
        payload = {"_raw": resp.text}
    return resp.status_code, payload


def _find_existing_store_id(client: TestClient, *, token: str) -> Optional[int]:
    """
    Contract test 不硬编码 store_id。
    策略：
      1) 如果设置 STORE_ID_FOR_CONTRACT，优先用它（且必须存在）
      2) 尝试常见 store_id（1..30 + 常用 demo id）
      3) 若找不到，跳过（说明该测试环境未 seed stores）
    """
    v = (os.getenv("STORE_ID_FOR_CONTRACT") or "").strip()
    if v:
        try:
            sid = int(v)
        except Exception:
            sid = -1
        if sid >= 1:
            code, _ = _try_get_options(client, token=token, store_id=sid)
            if code != 404:
                return sid
            # 明确指定但不存在：让测试失败，提示修正 seed 或 env
            pytest.fail(f"STORE_ID_FOR_CONTRACT={sid} but store not found (404)")

    # 常见候选：优先小范围，避免 testserver 里跑太多请求
    candidates: List[int] = []
    candidates.extend([1, 2, 3, 10, 11, 12, 100, 101, 900, 915, 916])
    candidates.extend(list(range(1, 31)))

    seen: set[int] = set()
    for sid in candidates:
        if sid in seen or sid < 1:
            continue
        seen.add(sid)
        code, _ = _try_get_options(client, token=token, store_id=sid)
        if code != 404:
            return sid

    return None


def test_order_sim_filled_code_options_contract() -> None:
    """
    Contract:
      GET /stores/{store_id}/order-sim/filled-code-options

    Response model:
      { ok: true, data: { items: [{ filled_code, suggested_title, components_summary }, ...] } }

    Guarantees:
      - items are sorted by filled_code asc
      - filled_code unique
      - only these 3 keys appear in each item
    """
    client = TestClient(app)
    token = _login_and_get_token(client)

    store_id = _find_existing_store_id(client, token=token)
    if store_id is None:
        pytest.skip("No seeded store found for /stores/{id}/order-sim/filled-code-options contract test")

    status, payload = _try_get_options(client, token=token, store_id=store_id)
    assert status == 200, payload

    assert isinstance(payload, dict), payload
    assert payload.get("ok") is True, payload

    data = payload.get("data")
    assert isinstance(data, dict), payload
    items = data.get("items")
    assert isinstance(items, list), payload

    # items 可为空（该店铺尚未绑定任何 merchant_code），结构必须稳定
    if not items:
        return

    allowed_keys = {"filled_code", "suggested_title", "components_summary"}

    filled_codes: List[str] = []
    for it in items:
        assert isinstance(it, dict), it
        assert set(it.keys()) == allowed_keys, it

        fc = it.get("filled_code")
        st = it.get("suggested_title")
        cs = it.get("components_summary")

        assert isinstance(fc, str) and fc.strip(), it
        assert isinstance(st, str), it
        assert isinstance(cs, str), it

        filled_codes.append(fc)

    # filled_code 唯一 + 升序（后端 ORDER BY 约束）
    assert len(set(filled_codes)) == len(filled_codes), filled_codes
    assert filled_codes == sorted(filled_codes), filled_codes
