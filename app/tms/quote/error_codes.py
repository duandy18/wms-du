from __future__ import annotations


class QuoteCalcErrorCode:
    TEMPLATE_NOT_FOUND = "QUOTE_CALC_TEMPLATE_NOT_FOUND"
    TEMPLATE_NOT_EFFECTIVE = "QUOTE_CALC_TEMPLATE_NOT_EFFECTIVE"
    NO_MATCHING_ZONE = "QUOTE_CALC_NO_MATCHING_ZONE"
    NO_MATCHING_BRACKET = "QUOTE_CALC_NO_MATCHING_BRACKET"
    INVALID = "QUOTE_CALC_INVALID"
    FAILED = "QUOTE_CALC_FAILED"


def map_calc_value_error_to_code(msg: str) -> str:
    m = (msg or "").lower()
    if "template not found" in m:
        return QuoteCalcErrorCode.TEMPLATE_NOT_FOUND
    if "template not effective" in m or "template archived" in m:
        return QuoteCalcErrorCode.TEMPLATE_NOT_EFFECTIVE
    if "no matching zone" in m or "no matching destination group" in m:
        return QuoteCalcErrorCode.NO_MATCHING_ZONE
    if "no matching bracket" in m or "no matching pricing matrix" in m:
        return QuoteCalcErrorCode.NO_MATCHING_BRACKET
    return QuoteCalcErrorCode.INVALID
