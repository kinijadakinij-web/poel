import os
from fastapi import APIRouter, Request, Query
from typing import Optional

from services.database import db_get_signals
from services.auth_service import decode_token, get_admin_id

router = APIRouter()

def _get_user_id_from_request(request: Request) -> Optional[str]:
    if request is None:
        return None
    token = request.headers.get("authorization", "")
    if token.startswith("Bearer "):
        payload = decode_token(token[7:])
        if payload:
            return payload.get("sub")
    user_param = request.query_params.get("user")
    return user_param if user_param else None

def _resolve_user_id(request: Request, user_query: Optional[str]) -> Optional[str]:
    """
    Private mode: user login → data milik dia.
    Public mode: gak login → data admin (dari cache startup).
    """
    user_id = user_query or _get_user_id_from_request(request)
    if user_id:
        return user_id
    return get_admin_id()

def _pnl(s):
    return float(s.get("pnl_pct") or 0)

@router.get("/signals")
async def get_signal_history(
    limit: int = 100,
    request: Request = None,
    user: Optional[str] = Query(None)
):
    user_id = _resolve_user_id(request, user)
    signals = db_get_signals(user_id=user_id, limit=limit)
    return {"data": signals, "total": len(signals)}

@router.get("/signals/{symbol}")
async def get_signal_history_by_symbol(
    symbol: str,
    limit: int = 100,
    request: Request = None,
    user: Optional[str] = Query(None)
):
    user_id = _resolve_user_id(request, user)
    all_signals = db_get_signals(user_id=user_id, limit=1000)
    signals = [s for s in all_signals if s.get("symbol") == symbol]
    return {"data": signals[:limit], "total": len(signals)}

@router.get("/summary")
async def get_summary_all(
    request: Request = None,
    user: Optional[str] = Query(None)
):
    user_id = _resolve_user_id(request, user)
    signals = db_get_signals(user_id=user_id, limit=10000)

    closed = [s for s in signals if s.get("result") in ("TP", "SL")]
    wins = [s for s in closed if s.get("result") == "TP"]
    losses = [s for s in closed if s.get("result") == "SL"]
    open_sig = [s for s in signals if s.get("status") == "OPEN"]

    total_pnl = sum(_pnl(s) for s in closed)
    winrate = round(len(wins) / len(closed) * 100, 2) if closed else 0.0
    avg_pnl = round(total_pnl / len(closed), 4) if closed else 0.0

    return {
        "data": {
            "total_signals": len(signals),
            "closed_trades": len(closed),
            "open_signals": len(open_sig),
            "wins": len(wins),
            "losses": len(losses),
            "winrate": winrate,
            "total_pnl_pct": round(total_pnl, 4),
            "avg_pnl_pct": avg_pnl,
        }
    }

@router.get("/summary/{symbol}")
async def get_summary_by_symbol(
    symbol: str,
    request: Request = None,
    user: Optional[str] = Query(None)
):
    user_id = _resolve_user_id(request, user)
    all_signals = db_get_signals(user_id=user_id, limit=10000)
    signals = [s for s in all_signals if s.get("symbol") == symbol]

    closed = [s for s in signals if s.get("result") in ("TP", "SL")]
    wins = [s for s in closed if s.get("result") == "TP"]
    losses = [s for s in closed if s.get("result") == "SL"]

    total_pnl = sum(_pnl(s) for s in closed)
    winrate = round(len(wins) / len(closed) * 100, 2) if closed else 0.0
    avg_pnl = round(total_pnl / len(closed), 4) if closed else 0.0

    return {
        "data": {
            "symbol": symbol,
            "closed_trades": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "winrate": winrate,
            "total_pnl_pct": round(total_pnl, 4),
            "avg_pnl_pct": avg_pnl,
        }
    }
