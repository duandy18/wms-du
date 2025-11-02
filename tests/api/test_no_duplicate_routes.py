from app.main import app


def test_no_duplicate_routes():
    """检测是否有重复的 HTTP 路由（方法+路径）"""
    seen = {}
    dups = []
    for r in app.router.routes:
        path = getattr(r, "path", None)
        methods = getattr(r, "methods", set())
        if not path or not methods:
            continue
        for m in methods:
            key = (m.upper(), path)
            if key in seen:
                dups.append((key, seen[key], r.name))
            else:
                seen[key] = r.name
    assert not dups, f"Duplicate routes: {dups}"
