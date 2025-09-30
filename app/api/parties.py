# app/api/parties.py
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.parties import Party
from app.schemas.parties import PartyCreate, PartyOut

router = APIRouter()


@router.post("/parties", response_model=PartyOut, status_code=201)
def create_party(party_in: PartyCreate, db: Session = Depends(get_db)):
    """
    创建一个新的供应商或客户。
    """
    db_party = Party(**party_in.model_dump())
    db_party.id = str(uuid4())  # 为新实体生成一个唯一ID
    db.add(db_party)
    db.commit()
    db.refresh(db_party)
    return db_party


@router.get("/parties", response_model=list[PartyOut])
def get_all_parties(db: Session = Depends(get_db)):
    """
    获取所有供应商和客户的列表。
    """
    return db.query(Party).all()


@router.get("/parties/{party_id}", response_model=PartyOut)
def get_party_by_id(party_id: str, db: Session = Depends(get_db)):
    """
    通过ID获取单个供应商或客户。
    """
    party = db.query(Party).filter(Party.id == party_id).first()
    if not party:
        raise HTTPException(status_code=404, detail="Party not found")
    return party
