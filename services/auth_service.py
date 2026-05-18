import os
import uuid
import time
import jwt
import bcrypt
from typing import Optional, Dict, Any

from services.database import get_user_by_username, get_user_by_id, create_user, update_user

JWT_SECRET = os.getenv("JWT_SECRET", "agent-x-secret-change-me-in-production")
JWT_ALGO = "HS256"
JWT_EXPIRY = 86400 * 7  # 7 hari

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSKEY = os.getenv("ADMIN_PASSKEY", "admin123")

# ── Baca env variables untuk trading config ──
ADMIN_INITIAL_BALANCE = float(os.getenv("INITIAL_BALANCE", "1000"))
ADMIN_LEVERAGE = int(os.getenv("TRADE_LEVERAGE", "10"))
ADMIN_MARGIN = float(os.getenv("TRADE_ENTRY_USDT", "100"))

# ── Global admin ID (di-set saat startup) ──
_admin_id: Optional[str] = None

def get_admin_id() -> Optional[str]:
    """Return admin user ID yang di-cache saat startup."""
    return _admin_id

def hash_passkey(passkey: str) -> str:
    return bcrypt.hashpw(passkey.encode(), bcrypt.gensalt()).decode()

def verify_passkey(passkey: str, hashed: str) -> bool:
    return bcrypt.checkpw(passkey.encode(), hashed.encode())

def create_token(user_id: str, username: str, is_admin: bool) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "username": username,
        "is_admin": is_admin,
        "iat": now,
        "exp": now + JWT_EXPIRY,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)

def decode_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except Exception:
        return None

def authenticate_user(username: str, passkey: str) -> Optional[Dict[str, Any]]:
    user = get_user_by_username(username)
    if not user:
        return None
    if verify_passkey(passkey, user["passkey_hash"]):
        return user
    return None

def seed_admin():
    global _admin_id
    existing = get_user_by_username(ADMIN_USERNAME)
    
    if not existing:
        # ── Create admin baru pakai env values ──
        uid = str(uuid.uuid4())
        create_user(
            user_id=uid,
            username=ADMIN_USERNAME,
            passkey_hash=hash_passkey(ADMIN_PASSKEY),
            is_admin=1,
            leverage=ADMIN_LEVERAGE,
            margin=ADMIN_MARGIN,
            balance=ADMIN_INITIAL_BALANCE,
        )
        _admin_id = uid
        print(f"[Auth] Admin seeded: {ADMIN_USERNAME} ({_admin_id}) | "
              f"balance={ADMIN_INITIAL_BALANCE}, leverage={ADMIN_LEVERAGE}x, margin={ADMIN_MARGIN}")
    else:
        # ── Update admin existing dengan env values terbaru ──
        _admin_id = existing["id"]
        update_user(_admin_id, {
            "balance": ADMIN_INITIAL_BALANCE,
            "initial_balance": ADMIN_INITIAL_BALANCE,
            "leverage": ADMIN_LEVERAGE,
            "margin": ADMIN_MARGIN,
        })
        print(f"[Auth] Admin updated: {ADMIN_USERNAME} ({_admin_id}) | "
              f"balance={ADMIN_INITIAL_BALANCE}, leverage={ADMIN_LEVERAGE}x, margin={ADMIN_MARGIN}")
