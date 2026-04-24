# app/user/models/page_registry.py
# Domain move: PageRegistry ORM belongs to user navigation runtime.
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import Boolean, CheckConstraint, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db.base import Base


class PageRegistry(Base):
    """
    页面注册表（层级页面真身）。

    当前主线：
    - 一级页面 = 权限主边界
    - 二级页面 = 业务组，或二级主页面
    - 三级页面 = 具体业务页
    - 二级、三级页面默认继承一级页面权限
    """

    __tablename__ = "page_registry"

    __table_args__ = (
        CheckConstraint(
            "domain_code IN ('analytics', 'oms', 'pms', 'procurement', 'wms', 'tms', 'admin', 'inbound')",
            name="ck_page_registry_domain_code",
        ),
        CheckConstraint(
            "level IN (1, 2, 3)",
            name="ck_page_registry_level",
        ),
        CheckConstraint(
            "((level = 1 AND parent_code IS NULL) OR (level IN (2, 3) AND parent_code IS NOT NULL))",
            name="ck_page_registry_parent_level_consistency",
        ),
        CheckConstraint(
            "("
            "(inherit_permissions = TRUE AND read_permission_id IS NULL AND write_permission_id IS NULL) "
            "OR "
            "(inherit_permissions = FALSE AND read_permission_id IS NOT NULL AND write_permission_id IS NOT NULL)"
            ")",
            name="ck_page_registry_permission_inherit_consistency",
        ),
        sa.Index("ix_page_registry_parent_code", "parent_code"),
    )

    code = Column(String(64), primary_key=True)
    name = Column(String(64), nullable=False)

    parent_code = Column(
        String(64),
        ForeignKey(
            "page_registry.code",
            name="fk_page_registry_parent_code_page_registry",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    level = Column(Integer, nullable=False)
    domain_code = Column(String(32), nullable=False)

    show_in_topbar = Column(Boolean, nullable=False)
    show_in_sidebar = Column(Boolean, nullable=False)
    inherit_permissions = Column(Boolean, nullable=False)

    read_permission_id = Column(
        Integer,
        ForeignKey(
            "permissions.id",
            name="fk_page_registry_read_permission_id_permissions",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    write_permission_id = Column(
        Integer,
        ForeignKey(
            "permissions.id",
            name="fk_page_registry_write_permission_id_permissions",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    sort_order = Column(Integer, nullable=False, server_default="0")
    is_active = Column(Boolean, nullable=False, server_default="TRUE")

    # 自关联：父子页面（支持三级树）
    parent = relationship(
        "PageRegistry",
        remote_side=[code],
        back_populates="children",
        foreign_keys=[parent_code],
        lazy="joined",
    )

    children = relationship(
        "PageRegistry",
        back_populates="parent",
        foreign_keys="PageRegistry.parent_code",
        lazy="selectin",
    )

    # 权限引用
    read_permission = relationship(
        "Permission",
        foreign_keys=[read_permission_id],
        lazy="joined",
    )
    write_permission = relationship(
        "Permission",
        foreign_keys=[write_permission_id],
        lazy="joined",
    )

    # route_prefix 映射
    route_prefixes = relationship(
        "PageRoutePrefix",
        back_populates="page",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<PageRegistry code={self.code!r} level={self.level} "
            f"parent_code={self.parent_code!r} domain={self.domain_code!r}>"
        )
