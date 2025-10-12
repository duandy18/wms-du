from typing import Optional

class BarcodeResolver:
    def resolve(self, code: str) -> Optional[str]:
        code = code.strip()
        if not code or len(code) < 4:
            return None
        # 规则示例：纯数字→EAN；"SKU:" 前缀→直接 SKU
        if code.isdigit() and len(code) in (8, 12, 13):
            # TODO: 实际应查条码映射表
            return None  # 先返回 None，走 400
        if code.upper().startswith("SKU:"):
            return code.split(":", 1)[1].strip()
        return None
