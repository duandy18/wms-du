from sqlalchemy import Boolean, Column, String

from app.db import Base


class Item(Base):
    __tablename__ = "items"

    id = Column(String, primary_key=True, index=True)
    sku = Column(String, unique=True, index=True)  # Stock Keeping Unit
    name = Column(String, index=True)
    description = Column(String)
    unit_of_measure = Column(String)
    is_active = Column(Boolean(), default=True)
