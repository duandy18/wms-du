# app/user/models/page_route_prefix.py
# Domain move: PageRoutePrefix ORM belongs to user navigation runtime.
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db.base import Base


class PageRoutePrefix(Base):
    """
    路由前缀 -> 页面归属映射。

    当前主线：
    - route_prefix 真相源 = page_route_prefixes
    - 当前应指向二级页面
    """

    __tablename__ = "page_route_prefixes"

    __table_args__ = (
        sa.UniqueConstraint("route_prefix", name="uq_page_route_prefixes_route_prefix"),
        sa.Index("ix_page_route_prefixes_page_code", "page_code"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    page_code = Column(
        String(64),
        ForeignKey(
            "page_registry.code",
            name="fk_page_route_prefixes_page_code_page_registry",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    route_prefix = Column(String(255), nullable=False)
    sort_order = Column(Integer, nullable=False, server_default="0")
    is_active = Column(Boolean, nullable=False, server_default="TRUE")

    page = relationship(
        "PageRegistry",
        back_populates="route_prefixes",
        lazy="joined",
    )

    def __repr__(self) -> str:
        return (
            f"<PageRoutePrefix id={self.id} route_prefix={self.route_prefix!r} "
            f"page_code={self.page_code!r}>"
        )
