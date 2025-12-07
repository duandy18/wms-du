# app/domain/events_enums.py
from enum import Enum


class EventState(str, Enum):
    PAID = "PAID"
    ALLOCATED = "ALLOCATED"
    SHIPPED = "SHIPPED"
    VOID = "VOID"


class ErrorCode(str, Enum):
    ILLEGAL_TRANSITION = "ILLEGAL_TRANSITION"  # 非法跃迁
    OUT_OF_ORDER = "OUT_OF_ORDER"  # 乱序到达
    IDEMPOTENT_HIT = "IDEMPOTENT_HIT"  # 幂等命中（不算致命）
    SCHEMA_VALIDATION = "SCHEMA_VALIDATION"  # 负载/字段校验失败
    RATE_LIMITED = "RATE_LIMITED"  # 限流拒绝
    UPSTREAM_ERROR = "UPSTREAM_ERROR"  # 上游平台/网络错误
    FATAL = "FATAL"  # 明确不可恢复
