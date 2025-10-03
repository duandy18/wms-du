# app/schemas/parties.py

from pydantic import BaseModel

from app.models.parties import PartyType


class PartyCreate(BaseModel):
    name: str
    party_type: PartyType
    contact_person: str | None = None
    phone_number: str | None = None
    email: str | None = None
    address: str | None = None


class PartyOut(PartyCreate):
    id: str

    class Config:
        from_attributes = True
