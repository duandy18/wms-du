from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.orm import relationship

from app.db import Base


class Warehouse(Base):
    __tablename__ = "warehouses"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    address = Column(String)

    locations = relationship("Location", back_populates="warehouse")


class Location(Base):
    __tablename__ = "locations"

    id = Column(String, primary_key=True, index=True)
    name = Column(String)

    # 外键：将库位关联到其所属的仓库
    warehouse_id = Column(String, ForeignKey("warehouses.id"))

    warehouse = relationship("Warehouse", back_populates="locations")
