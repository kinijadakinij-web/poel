from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
import uuid

from services.auth_service import (
    authenticate_user, create_token, decode_token, hash_passkey
)
from services.database import create_user, get_user_by_id, get_user_by_username, list_users, update_user

router = APIRouter()

class LoginData(BaseModel):
    username: str
    passkey: str

class RegisterData(BaseModel):
    username: str
    passkey: str
    leverage: int = 10
    margin: float = 100
    balance: float = 1000

def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization scheme")
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

def require_admin(user=Depends(get_current_user)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

@router.post("/api/auth/login")
async def login(data: LoginData):
    user = authenticate_user(data.username, data.passkey)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or passkey")
    token = create_token(user["id"], user["username"], bool(user["is_admin"]))
    return {
        "success": True,
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "is_admin": bool(user["is_admin"]),
            "leverage": user["leverage"],
            "margin": user["margin"],
            "balance": user["balance"],
            "initial_balance": user["initial_balance"],
        }
    }

@router.post("/api/auth/register")
async def register(data: RegisterData, admin=Depends(require_admin)):
    if get_user_by_username(data.username):
        raise HTTPException(status_code=400, detail="Username already exists")
    uid = str(uuid.uuid4())
    create_user(
        user_id=uid,
        username=data.username,
        passkey_hash=hash_passkey(data.passkey),
        is_admin=0,
        leverage=data.leverage,
        margin=data.margin,
        balance=data.balance,
    )
    return {"success": True, "user_id": uid}

@router.get("/api/auth/me")
async def me(user=Depends(get_current_user)):
    return {
        "id": user["id"],
        "username": user["username"],
        "is_admin": bool(user["is_admin"]),
        "leverage": user["leverage"],
        "margin": user["margin"],
        "balance": user["balance"],
        "initial_balance": user["initial_balance"],
    }

@router.get("/api/auth/users")
async def get_users(admin=Depends(require_admin)):
    users = list_users()
    return {"data": [{k: u[k] for k in u if k != "passkey_hash"} for u in users]}

@router.post("/api/auth/users/{user_id}/update")
async def update_user_data(user_id: str, data: dict, admin=Depends(require_admin)):
    allowed = {"leverage", "margin", "balance"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if updates:
        update_user(user_id, updates)
    return {"success": True}
