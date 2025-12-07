import pytest
from fastapi import FastAPI

from app.main import app  # 若路径不同，请按工程实际调整

# —— 内部路由白名单（FastAPI/Starlette 自带）——
_INTERNAL_PATH_PREFIXES = ("/openapi.json", "/docs", "/redoc", "/static")


def _iter_routes(app: FastAPI):
    for r in app.routes:
        methods = getattr(r, "methods", None) or []
        path = getattr(r, "path", getattr(r, "path_format", None))
        name = getattr(r, "name", None)
        endpoint = getattr(r, "endpoint", None)
        yield r, methods, path, name, endpoint


def _is_internal(path: str | None) -> bool:
    if not path:
        return True
    return any(path.startswith(p) for p in _INTERNAL_PATH_PREFIXES)


def test_no_conflicting_method_path_pairs():
    """
    允许同一 (METHOD, PATH) 被重复注册到“同一个 endpoint”（典型：多次 include_router），
    但禁止被注册到“不同 endpoint”（风险：阴影路由/行为分叉）。
    """
    mapping: dict[tuple[str, str], set[int]] = {}
    for _r, methods, path, _name, endpoint in _iter_routes(app):
        if _is_internal(path):
            continue
        for m in methods:
            key = (m.upper(), path)
            mapping.setdefault(key, set()).add(id(endpoint))

    conflicts = {key: ids for key, ids in mapping.items() if len(ids) > 1}
    assert not conflicts, (
        "Conflicting (METHOD, PATH) routes found (mapped to different endpoints): "
        f"{sorted(conflicts.keys())}"
    )


def test_route_names_unique_or_same_endpoint():
    """
    允许重复的 route name，只要它们指向同一个 endpoint。
    若同名路由指向不同 endpoint，则判定为冲突。
    """
    name_to_eps: dict[str, set[int]] = {}
    for _r, _methods, path, name, endpoint in _iter_routes(app):
        if not name or _is_internal(path):
            continue
        name_to_eps.setdefault(name, set()).add(id(endpoint))

    conflicts = {name: ids for name, ids in name_to_eps.items() if len(ids) > 1}
    assert (
        not conflicts
    ), f"Duplicate route names mapped to different endpoints: {sorted(conflicts.keys())}"
