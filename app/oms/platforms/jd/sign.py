# app/oms/platforms/jd/sign.py
from __future__ import annotations

import hashlib
from typing import Any, Mapping


def _normalize_sign_value(value: Any) -> str:
    """
    JD sign 参与值规范化。

    当前策略：
    - None / 空字符串：不参与 sign（由上层过滤）
    - bool：转为小写 true / false
    - 其他：str(value)

    注意：
    - 这是第一阶段协议实现策略
    - 后续若京东真实联调发现需微调，再只改这一层
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def build_jd_sign(
    params: Mapping[str, Any],
    client_secret: str,
) -> str:
    """
    构建 JD / JOS sign。

    第一阶段实现口径：
    - 排除 sign 本身和空键
    - 排除 None / 空字符串
    - 其余参数按 key 升序拼接 key + value
    - 使用：secret + content + secret
    - MD5 后转大写

    注意：
    - 360buy_param_json 作为“单个字符串参数”参与签名
    - 不展开其内部 JSON 字段
    """
    items: list[tuple[str, str]] = []

    for key, value in params.items():
        if not key or key == "sign":
            continue
        if value is None:
            continue

        normalized = _normalize_sign_value(value)
        if normalized == "":
            continue

        items.append((str(key), normalized))

    items.sort(key=lambda item: item[0])

    content = "".join(f"{key}{value}" for key, value in items)
    message = f"{client_secret}{content}{client_secret}".encode("utf-8")
    return hashlib.md5(message).hexdigest().upper()
