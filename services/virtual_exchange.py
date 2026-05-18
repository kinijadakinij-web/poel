import logging
import os
from typing import Optional

from services.database import get_user_by_id, update_user

logger = logging.getLogger(__name__)

INITIAL_BALANCE  = float(os.getenv("INITIAL_BALANCE", "1000"))
TRADE_LEVERAGE   = int(os.getenv("TRADE_LEVERAGE",    "10"))
TRADE_ENTRY_USDT = float(os.getenv("TRADE_ENTRY_USDT","100"))

class VirtualExchange:
    def __init__(self):
        print(
            f"VirtualExchange ready | "
            f"global fallback balance={INITIAL_BALANCE} USDT | "
            f"leverage={TRADE_LEVERAGE}x | "
            f"entry={TRADE_ENTRY_USDT} USDT/trade"
        )

    def get_info(self, user_id: Optional[str] = None) -> dict:
        if user_id:
            user = get_user_by_id(user_id)
            if user:
                return {
                    "balance":         round(user["balance"], 4),
                    "initial_balance": user["initial_balance"],
                    "leverage":        user["leverage"],
                    "entry_usdt":      user["margin"],
                }
        return {
            "balance":         INITIAL_BALANCE,
            "initial_balance": INITIAL_BALANCE,
            "leverage":        TRADE_LEVERAGE,
            "entry_usdt":      TRADE_ENTRY_USDT,
        }

    def apply_result(
        self,
        result:      str,
        direction:   str,
        entry:       float,
        close_price: float,
        user_id:     Optional[str] = None,
    ) -> float:
        if result not in ("TP", "SL"):
            return 0.0
        if entry <= 0:
            return 0.0

        info = self.get_info(user_id)
        margin = min(info["entry_usdt"], max(info["balance"], 0))
        if margin <= 0:
            logger.warning("VirtualExchange: balance is 0 — trade PnL not applied")
            return 0.0

        if direction == "LONG":
            pnl_pct = (close_price - entry) / entry
        else:
            pnl_pct = (entry - close_price) / entry

        pnl_usdt = round(margin * info["leverage"] * pnl_pct, 4)
        new_balance = max(round(info["balance"] + pnl_usdt, 4), 0.0)

        if user_id:
            update_user(user_id, {"balance": new_balance})

        sign = "+" if pnl_usdt >= 0 else ""
        print(
            f"{result} | {direction} entry={entry} → {close_price} | "
            f"pnl={sign}{pnl_usdt} USDT | balance={new_balance} USDT"
            f"{' (user=' + user_id + ')' if user_id else ' (global)'}"
        )
        return pnl_usdt

    def reset(self, user_id: Optional[str] = None):
        if user_id:
            user = get_user_by_id(user_id)
            if user:
                update_user(user_id, {"balance": user["initial_balance"]})
                print(f"VirtualExchange: user {user_id} balance reset to {user['initial_balance']} USDT")
        else:
            print(f"VirtualExchange: global balance reset to {INITIAL_BALANCE} USDT")

virtual_exchange = VirtualExchange()
