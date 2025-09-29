from itertools import count

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr

router = APIRouter()


# --- Models ---
class UserCreate(BaseModel):
    username: str
    email: EmailStr


class UserOut(BaseModel):
    id: int
    username: str
    email: EmailStr


class UserUpdate(BaseModel):
    username: str
    email: EmailStr


# --- In-memory store on app.state ---
def _get_store(request: Request):
    """Ensure app.state.users_store exists (dict store + auto-increment id)."""
    if not hasattr(request.app.state, "users_store"):
        request.app.state.users_store = {
            "data": {},
            "id_gen": count(1),  # auto-increment id
        }
    return request.app.state.users_store


# --- Routes ---
@router.post("/", status_code=201, response_model=UserOut)
def create_user(payload: UserCreate, request: Request):
    store = _get_store(request)
    users: dict[int, dict] = store["data"]
    # username must be unique
    if any(u["username"] == payload.username for u in users.values()):
        raise HTTPException(status_code=409, detail="username already exists")
    uid = next(store["id_gen"])
    users[uid] = {"id": uid, "username": payload.username, "email": str(payload.email)}
    return users[uid]


@router.get("/", response_model=list[UserOut])
def list_users(request: Request):
    store = _get_store(request)
    users: dict[int, dict] = store["data"]
    # return in ascending id order
    return [UserOut(**users[k]) for k in sorted(users.keys())]


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: int, request: Request):
    store = _get_store(request)
    users: dict[int, dict] = store["data"]
    u = users.get(user_id)
    if not u:
        raise HTTPException(status_code=404, detail="user not found")
    return u


@router.put("/{user_id}", response_model=UserOut, status_code=200)
def update_user(user_id: int, payload: UserUpdate, request: Request):
    store = _get_store(request)
    users: dict[int, dict] = store["data"]
    u = users.get(user_id)
    if not u:
        raise HTTPException(status_code=404, detail="user not found")
    # username must be unique (excluding self)
    if any(
        v["username"] == payload.username and k != user_id for k, v in users.items()
    ):
        raise HTTPException(status_code=409, detail="username already exists")
    u["username"] = payload.username
    u["email"] = str(payload.email)
    return u


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, request: Request):
    store = _get_store(request)
    users: dict[int, dict] = store["data"]
    if user_id not in users:
        raise HTTPException(status_code=404, detail="user not found")
    del users[user_id]
    return Response(status_code=204)
