# app/schemas/parties.py


from pydantic import BaseModel, ConfigDict

from app.models.parties import PartyType


class PartyBase(BaseModel):
    name: str
    party_type: PartyType
    contact_person: str | None = None
    phone_number: str | None = None
    email: str | None = None
    address: str | None = None


class PartyCreate(PartyBase):
    pass


class PartyUpdate(PartyBase):
    name: str | None = None
    party_type: PartyType | None = None


class PartyOut(PartyBase):
    id: str

    model_config = ConfigDict(from_attributes=True)
