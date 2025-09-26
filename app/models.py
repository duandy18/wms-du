# app/models.py
"""
Expose SQLAlchemy Base, metadata, and a minimal User model.
This lets Alembic autogenerate/diff work, and `models.User` exists for routers.
"""

from __future__ import annotations

from sqlalchemy import Integer, MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"User(id={self.id!r}, username={self.username!r})"


# expose metadata (typed, two-step to keep mypy happy)
metadata: MetaData
metadata = Base.metadata
