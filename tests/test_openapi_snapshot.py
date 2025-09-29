# tests/test_openapi_snapshot.py
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

    # Compare API definition (info + required subset of path keys)
    assert current["info"] == snapshot["info"]

    current_paths = set(current["paths"].keys())
    required_paths = set(snapshot["paths"].keys())  # 快照里的路径必须都存在
    assert required_paths.issubset(current_paths)
