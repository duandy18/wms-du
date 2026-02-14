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


def _list_stores(client: TestClient, *, token: str) -> List[Dict[str, Any]]:
    """
    通过 /stores 列表拿到 shop_type，用于选择 TEST store。
    兼容返回形态：
      - { ok: true, data: [...] }
      - { ok: true, data: { items: [...] } }
      - 其它：尽量容错，返回空
    """
    resp = client.get("/stores", headers=_auth_headers(token))
    if resp.status_code != 200:
        return []
    try:
        payload = resp.json()
    except Exception:
        return []

    if not isinstance(payload, dict):
        return []

    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        rows = data.get("items") or []
    elif isinstance(data, list):
        rows = data
    else:
        return []

    out: List[Dict[str, Any]] = []
    for r in rows:
        if isinstance(r, dict):
            out.append(r)
    return out


def _extract_store_id(row: Dict[str, Any]) -> Optional[int]:
    sid = row.get("id")
    if sid is None:
        sid = row.get("store_id")
    if sid is None:
        return None
    try:
        x = int(sid)
    except Exception:
        return None
    return x if x >= 1 else None


def _is_test_store_row(row: Dict[str, Any]) -> bool:
    # /stores 已显性化 shop_type: TEST | PROD
    st = str(row.get("shop_type") or "").strip().upper()
    return st == "TEST"


def _find_existing_store_id(client: TestClient, *, token: str) -> Optional[int]:
    """
    Contract test 不硬编码 store_id，但 order-sim 已启用测试商铺门禁：
      - 必须选择一个 TEST store，否则 403 属于正确行为。

    策略：
      1) 如果设置 STORE_ID_FOR_CONTRACT，优先用它：
         - 必须存在（非 404）
         - 且必须能 200 访问 order-sim（即 TEST store）
         否则 fail，提示修正 seed 或 env。
      2) 否则从 /stores 中挑选第一个 shop_type=TEST 的 store_id，并验证其能 200 访问 order-sim。
      3) 若找不到 TEST store，则跳过（说明该测试环境未 seed TEST stores）。
    """
    v = (os.getenv("STORE_ID_FOR_CONTRACT") or "").strip()
    if v:
        try:
            sid = int(v)
        except Exception:
            sid = -1
        if sid >= 1:
            code, payload = _try_get_options(client, token=token, store_id=sid)
            if code == 404:
                pytest.fail(f"STORE_ID_FOR_CONTRACT={sid} but store not found (404)")
            if code == 403:
                pytest.fail(
                    f"STORE_ID_FOR_CONTRACT={sid} is not a TEST store (order-sim gate returns 403): {payload}"
                )
            if code != 200:
                pytest.fail(f"STORE_ID_FOR_CONTRACT={sid} unexpected status={code}: {payload}")
            return sid

    # 走 /stores 列表挑 TEST store
    rows = _list_stores(client, token=token)
    for r in rows:
        if not _is_test_store_row(r):
            continue
        sid = _extract_store_id(r)
        if sid is None:
            continue
        code, _payload = _try_get_options(client, token=token, store_id=sid)
        if code == 200:
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
        pytest.skip("No TEST store seeded; order-sim endpoints are gated to TEST stores only")

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
