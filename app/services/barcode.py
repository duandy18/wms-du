from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Callable, Optional


@dataclass
class ParsedBarcode:
    """
    结构化条码结果（供上层业务使用）。
    - sku:       直接识别或映射得到的 SKU
    - gtin:      EAN-8 / UPC-A(12) / EAN-13 识别出的 GTIN
    - batch:     批次号（来自 GS1 (10) 或 KV 码）
    - expiry:    到期日（来自 GS1 (17) 或 KV 码：YYYYMMDD/YYMMDD）
    - raw:       原始输入
    - kind:      码制/来源：'SKU','GS1','EAN8','UPC12','EAN13','KV','UNKNOWN'
    """

    sku: Optional[str]
    gtin: Optional[str]
    batch: Optional[str]
    expiry: Optional[date]
    raw: str
    kind: str


class BarcodeResolver:
    """
    v1.0 强契约版条码解析器
    - 兼容旧接口：resolve(code) -> Optional[str]（返回 SKU 或 None）
    - 新增 parse(code) -> ParsedBarcode（含 GTIN/批次/效期）
    - 可注入 gtin_to_sku 回调，将 GTIN 映射为 SKU（或返回 None）
    """

    _re_sku_prefix = re.compile(r"^\s*(SKU|ITEM)\s*:\s*(?P<sku>[A-Za-z0-9\-_\.]+)\s*$", re.I)
    _re_kv = re.compile(
        r"\b(?P<key>SKU|ITEM|BATCH|LOT|EXP|EXPIRE|EXPIRY)\b\s*[:=]\s*(?P<val>[A-Za-z0-9\-_\.]+)",
        re.I,
    )
    _re_gs1_ai = re.compile(r"\((\d{2})\)([^\(]+)")  # 形如 (01)123...(17)250101(10)LOT1

    def __init__(self, gtin_to_sku: Optional[Callable[[str], Optional[str]]] = None) -> None:
        self._gtin_to_sku = gtin_to_sku

    # ----------------------------- 兼容旧接口 -----------------------------

    def resolve(self, code: str) -> Optional[str]:
        """
        兼容旧用法：返回可判定的 SKU，否则 None。
        规则：
          1) "SKU:XXXX" / "ITEM:XXXX" 前缀直出
          2) GS1/GTIN 成功解析且可映射为 SKU（依赖回调）则返回
          3) KV 码（含 SKU/ITEM）返回对应值
          4) 其他返回 None
        """
        parsed = self.parse(code)
        return parsed.sku

    # ------------------------------- 新接口 -------------------------------

    def parse(self, code: str) -> ParsedBarcode:
        s = (code or "").strip()
        if not s or len(s) < 2:
            return ParsedBarcode(None, None, None, None, code, "UNKNOWN")

        # 1) 显式 SKU/ITEM 前缀
        m = self._re_sku_prefix.match(s)
        if m:
            sku = m.group("sku").strip()
            return ParsedBarcode(sku=sku, gtin=None, batch=None, expiry=None, raw=code, kind="SKU")

        # 2) GS1 AI（01=GTIN, 10=批次, 17=效期 YYMMDD）
        if "(" in s and ")" in s:
            gs1 = self._parse_gs1(s)
            if gs1:
                sku = gs1.sku or (
                    self._gtin_to_sku(gs1.gtin) if (self._gtin_to_sku and gs1.gtin) else None
                )
                return ParsedBarcode(
                    sku=sku, gtin=gs1.gtin, batch=gs1.batch, expiry=gs1.expiry, raw=code, kind="GS1"
                )

        # 3) 纯数字：尝试 GTIN（EAN-8/UPC-A(12)/EAN-13）
        if s.isdigit():
            kind = None
            if len(s) == 8 and self._valid_ean8(s):
                kind = "EAN8"
            elif len(s) == 12 and self._valid_upc12(s):
                kind = "UPC12"
            elif len(s) == 13 and self._valid_ean13(s):
                kind = "EAN13"

            if kind:
                sku = self._gtin_to_sku(s) if self._gtin_to_sku else None
                return ParsedBarcode(sku=sku, gtin=s, batch=None, expiry=None, raw=code, kind=kind)

        # 4) 简单 KV 码：SKU/ITEM/LOT/BATCH/EXP=...
        if any(sep in s for sep in ("|", ";", ",", "\n", " ")):
            kv = self._parse_kv(s)
            if kv:
                return kv

        # 5) 其他
        return ParsedBarcode(None, None, None, None, code, "UNKNOWN")

    # ------------------------------ Helpers ------------------------------

    def _parse_gs1(self, s: str) -> Optional[ParsedBarcode]:
        """
        解析最常用的 GS1 AI：
        - (01) GTIN-14/13/12/8（前导 0 可出现）
        - (10) 批次号（可变长，通常到下一个 AI 结束）
        - (17) 到期日 YYMMDD
        仅做轻量解析，不展开 FNC1 等复杂场景。
        """
        pairs = self._re_gs1_ai.findall(s)
        if not pairs:
            return None

        ai: dict[str, str] = {}
        for k, v in pairs:
            ai[k] = v.strip()

        gtin = ai.get("01")
        batch = ai.get("10")
        expiry = self._parse_expiry(ai.get("17"))

        # 校验 GTIN（如果长度符合则做检验位校验）
        kind = "GS1"
        if gtin:
            if len(gtin) in (8, 12, 13, 14):
                # 14 位可能是 GTIN-14，校验时截取后 13/12/8 做 Luhn（按 EAN13 规则）
                if len(gtin) == 14:
                    core = gtin[1:]
                else:
                    core = gtin
                if len(core) == 13 and not self._valid_ean13(core):
                    gtin = None
                elif len(core) == 12 and not self._valid_upc12(core):
                    gtin = None
                elif len(core) == 8 and not self._valid_ean8(core):
                    gtin = None

        return ParsedBarcode(sku=None, gtin=gtin, batch=batch, expiry=expiry, raw=s, kind=kind)

    def _parse_kv(self, s: str) -> Optional[ParsedBarcode]:
        """
        解析简单 KV 码：支持分隔符 | ; , 空格 换行
        例：
          SKU:777|BATCH:CC-01|EXP:20251231
          ITEM:ABC-01 LOT:X1 EXPIRY:251231
        """
        miter = self._re_kv.finditer(s.replace("/", "").replace("\\", ""))
        found = {}
        for m in miter:
            k = m.group("key").upper()
            v = m.group("val").strip()
            found[k] = v

        if not found:
            return None

        sku = found.get("SKU") or found.get("ITEM")
        batch = found.get("BATCH") or found.get("LOT")

        exp_raw = found.get("EXP") or found.get("EXPIRE") or found.get("EXPIRY")
        expiry = self._parse_expiry(exp_raw)

        return ParsedBarcode(sku=sku, gtin=None, batch=batch, expiry=expiry, raw=s, kind="KV")

    # --- 校验与日期解析 ---

    @staticmethod
    def _valid_ean13(gtin: str) -> bool:
        if not (gtin.isdigit() and len(gtin) == 13):
            return False
        digits = [int(c) for c in gtin]
        checksum = digits[-1]
        s = sum((3 if i % 2 else 1) * n for i, n in enumerate(digits[:-1]))
        return (10 - (s % 10)) % 10 == checksum

    @staticmethod
    def _valid_upc12(gtin: str) -> bool:
        # UPC-A 的校验与 EAN13 类似（12 位）
        if not (gtin.isdigit() and len(gtin) == 12):
            return False
        digits = [int(c) for c in gtin]
        checksum = digits[-1]
        # 位置从左到右：奇数位×3，偶数位×1（不含校验位）
        s = 0
        for i, n in enumerate(digits[:-1], start=1):
            s += (3 if i % 2 == 1 else 1) * n
        return (10 - (s % 10)) % 10 == checksum

    @staticmethod
    def _valid_ean8(gtin: str) -> bool:
        if not (gtin.isdigit() and len(gtin) == 8):
            return False
        digits = [int(c) for c in gtin]
        checksum = digits[-1]
        s = (
            3 * digits[0]
            + 1 * digits[1]
            + 3 * digits[2]
            + 1 * digits[3]
            + 3 * digits[4]
            + 1 * digits[5]
            + 3 * digits[6]
        )
        return (10 - (s % 10)) % 10 == checksum

    @staticmethod
    def _parse_expiry(raw: Optional[str]) -> Optional[date]:
        if not raw:
            return None
        s = raw.strip()
        # 支持 YYYYMMDD 或 YYMMDD
        try:
            if len(s) == 8 and s.isdigit():
                y = int(s[0:4])
                m = int(s[4:6])
                d = int(s[6:8])
                return date(y, m, d)
            if len(s) == 6 and s.isdigit():
                y = int(s[0:2])
                m = int(s[2:4])
                d = int(s[4:6])
                # GS1 (17) 是 YYMMDD：以 2000 为世纪（常见做法）
                return date(2000 + y, m, d)
        except ValueError:
            return None
        return None
