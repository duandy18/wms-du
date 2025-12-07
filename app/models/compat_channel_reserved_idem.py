from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase

# 注意：
# - 这张表的主键结构在你的库里未明确（常见是 (platform, shop_id, idempotency_key) 之类的自然键）。
# - Declarative ORM 必须有主键列才能安全映射。为避免误映射引起新一轮漂移，这里先给一个“抽象占位”，不参与映射。
# - 等你确认该表的主键/列结构，我们再把最小映射改成明确的列与主键，或直接用只读反射方案。


class _Base(DeclarativeBase):  # 独立基类，避免影响项目 Base
    pass


class ChannelReservedIdem(_Base):
    __abstract__ = True
    # __tablename__ = "channel_reserved_idem"
    __table_args__ = ({"info": {"skip_autogen": True}},)

    # TODO: 确认主键后补最小映射
