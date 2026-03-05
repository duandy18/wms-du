# app/services/order_ingest_routing/normalize.py
from __future__ import annotations

from typing import Mapping, Optional

# 中国省级行政区：标准全称集合（用于最终落库与路由匹配）
_CANONICAL = {
    # 直辖市
    "北京市",
    "天津市",
    "上海市",
    "重庆市",
    # 省
    "河北省",
    "山西省",
    "辽宁省",
    "吉林省",
    "黑龙江省",
    "江苏省",
    "浙江省",
    "安徽省",
    "福建省",
    "江西省",
    "山东省",
    "河南省",
    "湖北省",
    "湖南省",
    "广东省",
    "海南省",
    "四川省",
    "贵州省",
    "云南省",
    "陕西省",
    "甘肃省",
    "青海省",
    "台湾省",
    # 自治区
    "内蒙古自治区",
    "广西壮族自治区",
    "西藏自治区",
    "宁夏回族自治区",
    "新疆维吾尔自治区",
    # 特别行政区
    "香港特别行政区",
    "澳门特别行政区",
}

# 常见简称/别名 → 标准全称
_ALIAS = {
    # 直辖市（常见不带“市”）
    "北京": "北京市",
    "天津": "天津市",
    "上海": "上海市",
    "重庆": "重庆市",
    # 省（常见不带“省”）
    "河北": "河北省",
    "山西": "山西省",
    "辽宁": "辽宁省",
    "吉林": "吉林省",
    "黑龙江": "黑龙江省",
    "江苏": "江苏省",
    "浙江": "浙江省",
    "安徽": "安徽省",
    "福建": "福建省",
    "江西": "江西省",
    "山东": "山东省",
    "河南": "河南省",
    "湖北": "湖北省",
    "湖南": "湖南省",
    "广东": "广东省",
    "海南": "海南省",
    "四川": "四川省",
    "贵州": "贵州省",
    "云南": "云南省",
    "陕西": "陕西省",
    "甘肃": "甘肃省",
    "青海": "青海省",
    "台湾": "台湾省",
    # 自治区（常见简称）
    "内蒙古": "内蒙古自治区",
    "内蒙": "内蒙古自治区",
    "广西": "广西壮族自治区",
    "西藏": "西藏自治区",
    "宁夏": "宁夏回族自治区",
    "新疆": "新疆维吾尔自治区",
    # 港澳
    "香港": "香港特别行政区",
    "澳门": "澳门特别行政区",
}

_SUFFIX_TRIES = ("", "省", "市", "自治区", "特别行政区")


def normalize_province_name(raw: Optional[str]) -> Optional[str]:
    """
    Phase 5 合同（稳定版）：
    - province 必须来自订单 address.province（显式输入）
    - 不允许任何 env fallback（避免测试/运行期产生“暗门”）

    现实增强（Phase 2：normalize 层）：
    - 允许常见非标准写法（如“河北”“ 河北 ”“内蒙”）被规范化为标准全称；
    - ✅ 无法识别时不再返回 None：回退为“原始非空字符串（trim 后）”，交给上层路由用作 routing key。
      解释：路由的最终裁决应当来自 service_provinces / service_cities / city_split 等治理表；
      normalize 负责“尽量标准化”，但不能把非空输入变成缺失，从而提前触发 PROVINCE_MISSING_OR_INVALID。
    """
    if raw is None:
        return None

    s = str(raw).replace("\u3000", " ").strip()
    if not s:
        return None

    if s in _CANONICAL:
        return s

    hit = _ALIAS.get(s)
    if hit:
        return hit

    for suf in _SUFFIX_TRIES:
        cand = s if suf == "" else f"{s}{suf}"
        if cand in _CANONICAL:
            return cand

    # ✅ 回退：保留原始非空省份字符串作为 routing key（例如 UT-PROV-SVC / sandbox 自定义码）
    return s


def normalize_province_from_address(address: Optional[Mapping[str, str]]) -> Optional[str]:
    """
    Phase 5 合同（稳定版）：
    - province 必须来自订单 address.province（显式输入）
    - 不允许任何 env fallback（避免测试/运行期产生“暗门”）
    """
    if not address:
        return None
    return normalize_province_name(address.get("province"))


def normalize_city_from_address(address: Optional[Mapping[str, str]]) -> Optional[str]:
    """
    Phase 5 合同（稳定版）：
    - city 必须来自订单 address.city（显式输入）
    - 仅当省启用 city-split 时才会被要求；但 normalize 本身不做 fallback
    """
    if not address:
        return None
    raw = str(address.get("city") or "").strip()
    return raw or None
