# app/api/routers/shipping_quote_error_codes.py
from __future__ import annotations


class QuoteCalcErrorCode:
    SCHEME_NOT_FOUND = "QUOTE_CALC_SCHEME_NOT_FOUND"
    SCHEME_NOT_EFFECTIVE = "QUOTE_CALC_SCHEME_NOT_EFFECTIVE"
    NO_MATCHING_ZONE = "QUOTE_CALC_NO_MATCHING_ZONE"
    NO_MATCHING_BRACKET = "QUOTE_CALC_NO_MATCHING_BRACKET"

    # ✅ 新合同护栏：命中 Zone 但未绑定模板（二维工作台负责绑定）
    ZONE_TEMPLATE_REQUIRED = "QUOTE_CALC_ZONE_TEMPLATE_REQUIRED"

    INVALID = "QUOTE_CALC_INVALID"
    FAILED = "QUOTE_CALC_FAILED"


def map_calc_value_error_to_code(msg: str) -> str:
    m = (msg or "").lower()
    if "scheme not found" in m:
        return QuoteCalcErrorCode.SCHEME_NOT_FOUND
    if "scheme not effective" in m:
        return QuoteCalcErrorCode.SCHEME_NOT_EFFECTIVE
    if "no matching zone" in m:
        return QuoteCalcErrorCode.NO_MATCHING_ZONE
    if "no matching bracket" in m:
        return QuoteCalcErrorCode.NO_MATCHING_BRACKET

    # ✅ 与 app/services/shipping_quote/calc.py 对齐（稳定短语）
    if "zone template required" in m:
        return QuoteCalcErrorCode.ZONE_TEMPLATE_REQUIRED

    return QuoteCalcErrorCode.INVALID
