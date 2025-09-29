def test_export_openapi_smoke(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    data = r.json()
    assert "openapi" in data and isinstance(data, dict)
