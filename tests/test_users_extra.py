# tests/test_users_extra.py
import uuid

from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def test_create_conflict_username():
    u = f"bob_{uuid.uuid4().hex[:6]}"
    payload = {"username": u, "email": f"{u}@ex.com"}
    r1 = client.post("/users/", json=payload)
    assert r1.status_code in (200, 201)

    r2 = client.post("/users/", json=payload)
    assert r2.status_code == 409
    assert "exists" in r2.json().get("detail", "").lower()


def test_create_invalid_email_422():
    u = f"eve_{uuid.uuid4().hex[:6]}"
    bad = {"username": u, "email": "not-an-email"}
    r = client.post("/users/", json=bad)
    assert r.status_code == 422
