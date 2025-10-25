# app/models/party.py
import enum
from sqlalchemy import Column, Enum, String
from app.db.base import Base


class PartyType(enum.Enum):
    SUPPLIER = "supplier"
    CUSTOMER = "customer"
    BOTH = "both"


class Party(Base):
    __tablename__ = "parties"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    party_type = Column(Enum(PartyType), nullable=False)
    contact_person = Column(String)
    phone_number = Column(String)
    email = Column(String, unique=True, nullable=True)
    address = Column(String)
