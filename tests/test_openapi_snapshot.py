import json

from fastapi.testclient import TestClient

from app.main import app


def test_openapi_snapshot():
    client = TestClient(app)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200

    current = resp.json()
    with open("tests/snapshots/openapi_snapshot.json", encoding="utf-8") as f:
        snapshot = json.load(f)

    # Compare API definition (info + set of path keys)
    assert current["info"] == snapshot["info"]
    assert set(current["paths"].keys()) == set(snapshot["paths"].keys())
