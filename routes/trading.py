from fastapi import APIRouter, Request, Query
from typing import Optional

from services.virtual_exchange import virtual_exchange, INITIAL_BALANCE
from services.database import db_get_signals, get_user_by_id
from services.auth_service import decode_token, get_admin_id

router = APIRouter()

def _get_user_id(request: Request) -> Optional[str]:
    token = request.headers.get("authorization", "")
    if token.startswith("Bearer "):
        payload = decode_token(token[7:])
        if payload:
            return payload.get("sub")
    user_param = request.query_params.get("user")
    return user_param if user_param else None

def _resolve_user_id(request: Request, user_query: Optional[str]) -> Optional[str]:
    user_id = user_query or _get_user_id(request)
    if user_id:
        return user_id
    return get_admin_id()

@router.get("/balance")
async def get_balance(request: Request, user: Optional[str] = Query(None)):
    user_id = _resolve_user_id(request, user)
    return {"data": virtual_exchange.get_info(user_id)}

@router.get("/positions")
async def get_positions(request: Request, user: Optional[str] = Query(None)):
    user_id = _resolve_user_id(request, user)
    signals = db_get_signals(user_id=user_id, status="OPEN", limit=100)

    positions = []
    for s in signals:
        entry = float(s.get("entry") or s.get("current_price") or 0)
        info = virtual_exchange.get_info(user_id)
        positions.append({
            "id": s["id"],
            "symbol": s["symbol"],
            "direction": s["decision"],
            "entry": entry,
            "tp": s.get("tp"),
            "sl": s.get("sl"),
            "invalidation": s.get("invalidation"),
            "entry_hit": bool(s.get("entry_hit", 0)),
            "confidence": s.get("confidence"),
            "opened_at": s.get("timestamp"),
            "margin_usdt": info["entry_usdt"],
            "leverage": info["leverage"],
        })

    return {"data": positions, "total": len(positions)}

@router.get("/history")
async def get_trade_history(limit: int = 50, request: Request = None, user: Optional[str] = Query(None)):
    user_id = _resolve_user_id(request, user)
    signals = db_get_signals(user_id=user_id, limit=1000)
    closed = [s for s in signals if s.get("result") in ("TP", "SL")]
    return {"data": closed[:limit], "total": len(closed)}

@router.get("/settings")
async def get_settings(request: Request, user: Optional[str] = Query(None)):
    user_id = _resolve_user_id(request, user)
    info = virtual_exchange.get_info(user_id)
    return {
        "data": {
            "initial_balance": info["initial_balance"],
            "leverage": info["leverage"],
            "entry_usdt": info["entry_usdt"],
            "note": (
                "Set INITIAL_BALANCE, TRADE_LEVERAGE, TRADE_ENTRY_USDT "
                "in your Railway environment variables."
            ),
        }
    }

@router.post("/reset-balance")
async def reset_balance(request: Request, user: Optional[str] = Query(None)):
    user_id = _resolve_user_id(request, user)
    virtual_exchange.reset(user_id)
    return {"ok": True, "balance": virtual_exchange.get_info(user_id)["balance"]}
