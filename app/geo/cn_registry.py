# app/geo/cn_registry.py
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class GeoItem:
    code: str
    name: str


def _norm(s: Optional[str]) -> str:
    return (s or "").strip()


def _repo_root() -> Path:
    # app/geo/cn_registry.py -> app/geo -> app -> repo root
    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def load_cn_geo() -> Tuple[List[GeoItem], Dict[str, List[GeoItem]]]:
    root = _repo_root()
    provinces_path = root / "app" / "resources" / "geo" / "cn_provinces.json"
    cities_path = root / "app" / "resources" / "geo" / "cn_cities.json"

    provinces_raw = json.loads(provinces_path.read_text(encoding="utf-8"))
    cities_raw = json.loads(cities_path.read_text(encoding="utf-8"))

    provinces: List[GeoItem] = []
    for x in provinces_raw:
        code = _norm(x.get("code"))
        name = _norm(x.get("name"))
        if code and name:
            provinces.append(GeoItem(code=code, name=name))

    cities_by_prov: Dict[str, List[GeoItem]] = {}
    for prov_code, arr in cities_raw.items():
        p = _norm(prov_code)
        out: List[GeoItem] = []
        if isinstance(arr, list):
            for x in arr:
                code = _norm(x.get("code"))
                name = _norm(x.get("name"))
                if code and name:
                    out.append(GeoItem(code=code, name=name))
        cities_by_prov[p] = out

    return provinces, cities_by_prov


# ✅ 常见简称/别名映射（只做最小集合，后续可扩充）
_PROVINCE_ALIASES: Dict[str, str] = {
    "宁夏": "宁夏回族自治区",
    "内蒙": "内蒙古自治区",
    "内蒙古": "内蒙古自治区",
    "新疆": "新疆维吾尔自治区",
    "广西": "广西壮族自治区",
    "北京": "北京市",
    "上海": "上海市",
    "天津": "天津市",
    "重庆": "重庆市",
}


def list_provinces(q: Optional[str] = None) -> List[GeoItem]:
    provinces, _ = load_cn_geo()
    t = _norm(q)
    if not t:
        return provinces

    t2 = _PROVINCE_ALIASES.get(t, t)
    t2 = _norm(t2)
    return [p for p in provinces if t2 in p.name or t2.lower() in p.code.lower()]


def list_cities(province_code: str, q: Optional[str] = None) -> List[GeoItem]:
    _, cities_by_prov = load_cn_geo()
    pc = _norm(province_code)
    arr = cities_by_prov.get(pc, [])
    t = _norm(q)
    if not t:
        return arr
    return [c for c in arr if t in c.name or t.lower() in c.code.lower()]


def resolve_province(code: Optional[str], name: Optional[str]) -> Optional[GeoItem]:
    provinces, _ = load_cn_geo()

    c = _norm(code)
    if c:
        for p in provinces:
            if p.code == c:
                return p
        return None

    n = _norm(name)
    if not n:
        return None
    n2 = _PROVINCE_ALIASES.get(n, n)
    for p in provinces:
        if p.name == n2:
            return p
    # 允许唯一包含匹配（只在唯一命中时）
    hits = [p for p in provinces if n2 in p.name]
    if len(hits) == 1:
        return hits[0]
    return None


def resolve_city(province_code: str, code: Optional[str], name: Optional[str]) -> Optional[GeoItem]:
    arr = list_cities(province_code)

    c = _norm(code)
    if c:
        for x in arr:
            if x.code == c:
                return x
        return None

    n = _norm(name)
    if not n:
        return None
    for x in arr:
        if x.name == n:
            return x
    hits = [x for x in arr if n in x.name]
    if len(hits) == 1:
        return hits[0]
    return None
