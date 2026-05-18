from fastapi import APIRouter, Request, Depends
from typing import List

from services.token_manager import token_manager
from services.qwen_ai import qwen_ai
from services.position_ai import position_ai
from routes.auth_routes import require_admin  # ← JWT guard

router = APIRouter()


@router.get("/tokens")
async def get_tokens(admin=Depends(require_admin)):
    """Get current token slots (masked). Admin only."""
    tokens = token_manager.get_tokens()
    masked = []
    for i, t in enumerate(tokens, 1):
        masked.append({
            "slot": i,
            "token": f"{t[:8]}...{t[-4:]}" if len(t) > 12 else "***",
            "active": True,
        })
    # Tambah slot kosong
    for i in range(len(tokens) + 1, 6):
        masked.append({"slot": i, "token": None, "active": False})
    return {"data": masked}


@router.post("/tokens")
async def update_tokens(request: Request, admin=Depends(require_admin)):
    """Update Qwen tokens. Admin only."""
    body = await request.json()
    tokens = body.get("tokens", [])

    # Validasi minimal 1 token
    valid = [t.strip() for t in tokens if t and len(t.strip()) > 20]
    if not valid:
        return {"ok": False, "detail": "At least 1 valid token required"}

    # Update DB + memory
    token_manager.update_tokens(valid)

    # Hot-reload Qwen AI clients
    qwen_ai.reload_tokens()
    # Hot-reload PositionAI token pool (kalau tidak pakai MONITOR_TOKEN dedicated)
    position_ai.reload_tokens()

    return {
        "ok": True,
        "message": f"{len(valid)} token(s) updated & reloaded",
        "tokens": [f"{t[:8]}...{t[-4:]}" for t in valid],
    }


@router.get("/tokens/status")
async def get_token_status(admin=Depends(require_admin)):
    """Get exhausted/active status per token slot. Admin only."""
    statuses = []
    for client in qwen_ai.clients:
        statuses.append({
            "slot": client.slot,
            "exhausted": client.exhausted,
        })
    return {"data": statuses, "total": len(statuses)}


@router.post("/tokens/reset-exhausted")
async def reset_exhausted(admin=Depends(require_admin)):
    """Reset semua exhausted flag. Admin only."""
    for client in qwen_ai.clients:
        client.exhausted = False
    position_ai.reset_exhausted()
    return {"ok": True, "message": f"{len(qwen_ai.clients)} qwen + position_ai token slot(s) reset"}
