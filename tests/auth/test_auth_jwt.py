from fastapi.testclient import TestClient
from app.main import app  # 你的入口在 app/main.py

client = TestClient(app)

def test_register_then_login_and_access_protected():
    # 1) 注册
    r = client.post("/auth/register", json={"username": "alice", "password": "secret123"})
    assert r.status_code in (200, 201), r.text

    # 2) 登录
    r = client.post("/auth/login", data={"username": "alice", "password": "secret123"})
    assert r.status_code == 200, r.text
    token = r.json().get("access_token")
    assert token and isinstance(token, str)

    # 3) 带 token 访问受保护接口（CI 默认关闭 /diag/secure，允许 404）
    r = client.get("/diag/secure", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code in (200, 404)
