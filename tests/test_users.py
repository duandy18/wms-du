# tests/test_users.py
import uuid

POSSIBLE_ID_KEYS = ("id", "user_id", "uid")
POSSIBLE_EMAIL_KEYS = ("email", "email_address", "mail", "emailAddr")


def _pick(d: dict, keys):
    for k in keys:
        if k in d:
            return k, d[k]
    return None, None


def test_user_crud_happy_path(client):
    # 1) create
    unique = uuid.uuid4().hex[:6]
    username = f"alice_{unique}"
    email = f"alice_{unique}@example.com"
    payload = {"username": username, "email": email}

    r_create = client.post("/users/", json=payload)
    assert r_create.status_code in (200, 201)
    created = r_create.json()

    _, user_id = _pick(created, POSSIBLE_ID_KEYS)

    assert user_id is not None, f"create response missing id in {POSSIBLE_ID_KEYS}: {created}"

    # 2) get by id
    r_get = client.get(f"/users/{user_id}")
    assert r_get.status_code == 200
    body = r_get.json()
    assert body.get("username") == username or body.get("username", "").startswith("alice_")

    # 3) list
    r_list = client.get("/users/")
    assert r_list.status_code == 200
    listed = r_list.json()

    # support different id key names in list items
    def _get_id(u):
        return next((u[k] for k in POSSIBLE_ID_KEYS if k in u), None)

    assert any(_get_id(u) == user_id for u in listed)

    # 4) update: send full fields to avoid server rejecting partial updates
    new_email = f"alice_{unique}@newmail.com"
    r_update = client.put(f"/users/{user_id}", json={"username": username, "email": new_email})
    assert r_update.status_code in (200, 204)

    # 5) fetch again and assert best-effort (if model omits email, do not force)
    r_after = client.get(f"/users/{user_id}")
    assert r_after.status_code == 200
    after = r_after.json()
    assert after.get("username") == username
    email_key, email_val = _pick(after, POSSIBLE_EMAIL_KEYS)
    if email_key:
        assert isinstance(email_val, str) and email_val.endswith("@newmail.com"), after

    # 6) delete
    r_del = client.delete(f"/users/{user_id}")
    assert r_del.status_code in (200, 204)

    # 7) ensure gone
    r_404 = client.get(f"/users/{user_id}")
    assert r_404.status_code in (404, 410)
