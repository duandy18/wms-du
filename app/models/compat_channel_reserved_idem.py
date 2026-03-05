from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase

# 注意：
# - 这是一个“抽象占位”模型，不参与真实映射（避免引入新一轮 schema 漂移）。
# - Declarative ORM 必须有主键列才能安全映射；这里故意不声明表名/列。
# - 等你确认该表的主键/列结构，我们再补最小映射，或改成只读反射方案。


class _Base(DeclarativeBase):  # 独立基类，避免影响项目 Base
    pass


class ChannelIdemRecord(_Base):
    __abstract__ = True
    __table_args__ = ({"info": {"skip_autogen": True}},)

    # TODO: 确认主键后补最小映射
