# tests/api/test_purchase_order_detail_base_contract.py
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict

from fastapi.testclient import TestClient

from app.main import app


def _login_and_get_token(client: TestClient) -> str:
    resp = client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data, dict)
    token = data.get("access_token")
    assert isinstance(token, str) and token.strip(), f"bad token payload: {data}"
    return token


def _auth_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _extract_po_id(payload: Dict[str, Any]) -> int:
    top_id = payload.get("id")
    if isinstance(top_id, int) and top_id > 0:
        return top_id
    if isinstance(top_id, str) and top_id.strip().isdigit():
        v = int(top_id)
        if v > 0:
            return v

    data = payload.get("data")
    if isinstance(data, dict):
        did = data.get("id") or data.get("po_id") or data.get("purchase_order_id")
        if isinstance(did, int) and did > 0:
            return did
        if isinstance(did, str) and did.strip().isdigit():
            v = int(did)
            if v > 0:
                return v
    return 0


def _assert_line_base_contract(line: Dict[str, Any]) -> None:
    for k in ("qty_ordered_base", "qty_received_base", "qty_remaining_base"):
        assert k in line, line
        assert isinstance(line[k], int), line

    ordered_base = int(line["qty_ordered_base"])
    received_base = int(line["qty_received_base"])
    remaining_base = int(line["qty_remaining_base"])

    assert ordered_base >= 0
    assert received_base >= 0
    assert remaining_base >= 0
    assert remaining_base == max(ordered_base - received_base, 0), line

    for k in ("qty_ordered", "qty_received", "qty_remaining"):
        assert k in line, line
        assert isinstance(line[k], int), line

    upc = line.get("units_per_case")
    if upc is not None:
        assert isinstance(upc, int), line
        assert upc >= 1, line

        received_purchase = received_base // upc
        expected_remaining_purchase = max(int(line["qty_ordered"]) - received_purchase, 0)

        assert int(line["qty_received"]) == received_purchase, line
        assert int(line["qty_remaining"]) == expected_remaining_purchase, line


def _pick_line_for_receive(lines: list[Dict[str, Any]]) -> Dict[str, Any]:
    # 优先选不需要有效期的商品，避免引入日期干扰
    for ln in lines:
        if not bool(ln.get("has_shelf_life") or False):
            return ln
    # 否则退而求其次：选第一条
    return lines[0]


def _build_receive_payload(line: Dict[str, Any]) -> Dict[str, Any]:
    line_id = int(line.get("id") or 0)
    assert line_id > 0, line

    payload: Dict[str, Any] = {"line_id": line_id, "qty": 1}

    has_sl = bool(line.get("has_shelf_life") or False)
    if not has_sl:
        return payload

    # ✅ 有效期商品：必须提供生产日期
    today = date.today()
    payload["production_date"] = today.isoformat()

    # 若无法推算到期（缺 value/unit），则兜底传 expiry_date
    sv = line.get("shelf_life_value")
    su = line.get("shelf_life_unit")
    if sv is None or su is None or not str(su).strip():
        payload["expiry_date"] = (today + timedelta(days=30)).isoformat()

    return payload


def test_purchase_order_detail_base_contract_and_receive_line_updates() -> None:
    client = TestClient(app)
    token = _login_and_get_token(client)

    r = client.post("/purchase-orders/dev-demo", headers=_auth_headers(token))
    assert r.status_code == 200, r.text
    po = r.json()
    assert isinstance(po, dict), po

    po_id = _extract_po_id(po)
    assert po_id > 0, f"failed to extract po_id from payload: {po}"

    r2 = client.get(f"/purchase-orders/{po_id}", headers=_auth_headers(token))
    assert r2.status_code == 200, r2.text
    detail = r2.json()
    assert isinstance(detail, dict), detail
    lines = detail.get("lines")
    assert isinstance(lines, list) and lines, detail

    for ln in lines:
        assert isinstance(ln, dict), ln
        _assert_line_base_contract(ln)

    target = _pick_line_for_receive(lines)
    payload = _build_receive_payload(target)

    rr = client.post(
        f"/purchase-orders/{po_id}/receive-line",
        headers=_auth_headers(token),
        json=payload,
    )
    assert rr.status_code == 200, rr.text
    detail2 = rr.json()
    assert isinstance(detail2, dict), detail2
    lines2 = detail2.get("lines")
    assert isinstance(lines2, list) and lines2, detail2

    for ln in lines2:
        assert isinstance(ln, dict), ln
        _assert_line_base_contract(ln)
