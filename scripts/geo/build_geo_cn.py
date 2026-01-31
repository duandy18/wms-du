# scripts/geo/build_geo_cn.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _norm(s: Any) -> str:
    return str(s or "").strip()


def _must_list(name: str, v: Any) -> List[Dict[str, Any]]:
    if not isinstance(v, list):
        raise SystemExit(f"unexpected {name} format (expected list)")
    out: List[Dict[str, Any]] = []
    for x in v:
        if isinstance(x, dict):
            out.append(x)
    return out


def _is_gb2260_6(code: str) -> bool:
    return len(code) == 6 and code.isdigit()


def _to_province_code_from_city_code(city_code: str) -> str:
    # 130100 -> 130000
    return city_code[:2] + "0000"


def main() -> None:
    root = _repo_root()
    vendor_dir = root / "app" / "resources" / "geo" / "vendor"

    prov_src = vendor_dir / "province-city-china.province.json"
    city_src = vendor_dir / "province-city-china.city.json"

    if not prov_src.exists():
        raise SystemExit(f"missing vendor file: {prov_src}")
    if not city_src.exists():
        raise SystemExit(f"missing vendor file: {city_src}")

    provinces_raw = _must_list("province.json", _read_json(prov_src))
    cities_raw = _must_list("city.json", _read_json(city_src))

    # province.json: [{code,name}, ...]，code 是 6 位 GB2260 省级码（xx0000）
    provinces: List[Dict[str, str]] = []
    prov_by_code: Dict[str, str] = {}

    bad_prov_code = 0
    for x in provinces_raw:
        code = _norm(x.get("code"))
        name = _norm(x.get("name"))
        if not code or not name:
            continue
        if not _is_gb2260_6(code):
            bad_prov_code += 1
            continue
        provinces.append({"code": code, "name": name})
        prov_by_code[code] = name

    # city.json: [{code,name,province:'13',city:'01'}, ...]
    # ✅ 以 city.code 推导 province_code：province_code = city_code[:2] + "0000"
    cities_by_prov: Dict[str, List[Dict[str, str]]] = {pc: [] for pc in prov_by_code.keys()}

    bad_city_code = 0
    unknown_prov = 0

    for x in cities_raw:
        code = _norm(x.get("code"))
        name = _norm(x.get("name"))
        if not code or not name:
            continue
        if not _is_gb2260_6(code):
            bad_city_code += 1
            continue

        prov_code = _to_province_code_from_city_code(code)
        if prov_code not in cities_by_prov:
            # 理论上不会发生（除非 vendor 省表缺了某省）
            unknown_prov += 1
            continue

        cities_by_prov[prov_code].append({"code": code, "name": name})

    # 排序：省按 code，市按 code
    provinces_sorted = sorted(provinces, key=lambda x: x["code"])
    for pc in list(cities_by_prov.keys()):
        cities_by_prov[pc] = sorted(cities_by_prov[pc], key=lambda x: x["code"])

    out_dir = root / "app" / "resources" / "geo"
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "cn_provinces.json").write_text(
        json.dumps(provinces_sorted, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "cn_cities.json").write_text(
        json.dumps(cities_by_prov, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"ok: wrote {out_dir / 'cn_provinces.json'}")
    print(f"ok: wrote {out_dir / 'cn_cities.json'}")
    print(f"provinces={len(provinces_sorted)} cities_total={sum(len(v) for v in cities_by_prov.values())}")
    print(f"debug: bad_prov_code={bad_prov_code} bad_city_code={bad_city_code} unknown_prov={unknown_prov}")


if __name__ == "__main__":
    main()
