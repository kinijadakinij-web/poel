"""
Position Monitor AI — HOLD or CLOSE untuk posisi yang sudah entry.

Features:
 • Multi-token pool (MONITOR_TOKEN_1..5, fallback ke QWEN_TOKEN_1..5 via token_manager)
 • Token rotation saat image_upload_failed — langsung coba token berikutnya
 • Pakai ai_lock() agar tidak bentrok dengan analysis AI
 • Retry terus sampai dapat HOLD/CLOSE/SL+ yang valid
 • Menyertakan opened_at, original_prompt, dan original_ai_response
 • SL+ enhanced: trigger SL+ ketika TP1 sudah tercapai dan PnL positif

Env vars:
 MONITOR_TOKEN_1..5 — bearer token khusus monitor (opsional)
 (kalau tidak diset, fallback ke QWEN_TOKEN_1..5 dari token_manager)
 MONITOR_INTERVAL_SECONDS — seberapa sering query per posisi (default: 120s)
 QWEN_BASE_URL / QWEN_MODEL / QWEN_THINKING_MODE — shared dengan qwen_ai.py
"""

import asyncio
import base64
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

from services.qwen_ai import (
    _draw_chart,
    HAS_CHARTS,
    QWEN_MODEL,
    QWEN_THINKING,
    _create_chat,
    _delete_chat,
    _upload_image_bytes,
    _send_stream,
)
from services.ai_lock import ai_lock

logger = logging.getLogger(__name__)

from services.token_manager import token_manager

MONITOR_INTERVAL = int(os.getenv("MONITOR_INTERVAL_SECONDS", "120"))

def _load_monitor_tokens() -> list[str]:
    """
    Load token pool untuk PositionAI.
    Priority:
      1. MONITOR_TOKEN_1..5 (khusus monitor, dari env)
      2. Fallback ke token_manager (QWEN_TOKEN_1..5)
    """
    monitor_tokens = []
    for i in range(1, 6):
        t = os.getenv(f"MONITOR_TOKEN_{i}", "").strip()
        if t:
            monitor_tokens.append(t)
    if monitor_tokens:
        print(f"[PositionAI] {len(monitor_tokens)} dedicated MONITOR_TOKEN(s) loaded | interval={MONITOR_INTERVAL}s")
        return monitor_tokens
    # Fallback ke qwen tokens
    qwen_tokens = token_manager.get_tokens()
    if qwen_tokens:
        print(f"[PositionAI] No MONITOR_TOKEN found — sharing {len(qwen_tokens)} QWEN_TOKEN(s) | interval={MONITOR_INTERVAL}s")
        return qwen_tokens
    print("[PositionAI] no token — set MONITOR_TOKEN_1 or QWEN_TOKEN_1")
    return []

_tokens: list[str] = _load_monitor_tokens()


# ---------------------------------------------------------------------------
# System prompt — position management with SL+ addition
# ---------------------------------------------------------------------------
POSITION_SYSTEM_PROMPT = """You are a position management AI for a crypto futures trading bot.

You are operating in a PERSISTENT TRADE ROOM — this conversation is dedicated to ONE open position.
This room was created when the trade was first entered.

HOW THIS ROOM WORKS:
 • The FIRST message in this conversation contains:
   - The original analysis AI prompt and response that justified entering this trade
   - The initial position status at entry time
 • Every subsequent message is a position UPDATE sent every {monitor_interval} seconds
 • Each update contains: current price, candle data, PnL, backend indicators
 • You have FULL CONTEXT of everything said in this room — use it
 • You already know the original thesis — do not ask for it again
 • When this trade closes, this room will be deleted

Because you can see the ENTIRE conversation history:
 → You know exactly WHY this trade was opened
 → You know all your previous HOLD/SL+ decisions and reasoning
 → You can see how price has evolved since entry
 → Be CONSISTENT with your previous reasoning unless market structure has genuinely changed

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DEFAULT BEHAVIOR — READ THIS FIRST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOLD is ALWAYS the default decision.
CLOSE is the exception — it requires MULTIPLE strong confirmations, not just one signal.
When in doubt between HOLD and CLOSE → choose HOLD.
Early patience protects the edge. Premature exits destroy it.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TIMEFRAME AUTHORITY RULE (CRITICAL)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The original trade thesis was built on a HIGHER TIMEFRAME (HTF) — typically 4H/1H structure.
Execution may have been on a lower timeframe (15m/3m), but the thesis is HTF.

RULE: CLOSE requires invalidation on the SAME or HIGHER timeframe as the original entry thesis.
  → 1m or 3m reversal signals alone are NEVER sufficient to CLOSE.
  → Lower timeframe signals (1m/3m) may justify SL+ or serve as WARNING only.
  → A micro_break on 1m/3m is NOISE — not thesis invalidation.
  → Only a structural break on 15m, 1H, or 4H can invalidate an HTF thesis.

Crypto futures behavior: 1m–3m candles routinely fake-break, sweep liquidity, then reclaim.
Do NOT treat a 1m micro_break the same as a 4H structure failure.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MINIMUM HOLD TIME RULE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
If position age < 5 minutes:
  → CLOSE is NOT allowed unless:
     a) Stop loss level is nearly hit (within 0.3% of SL)
     b) abnormal_move = true on a 15m+ timeframe
     c) HTF (15m or higher) structure is clearly invalidated
  → For all other signals in the first 5 minutes → HOLD

Reason: Most limit/void entries experience an initial fakeout or retrace before
moving to target. This is normal. The first 5 minutes are the highest-noise window.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
UNREALIZED PnL / ROE IS NOT STRUCTURAL INVALIDATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HIGH LEVERAGE AMPLIFIES NORMAL PRICE MOVEMENT.
With 50x leverage:
  - Price moves 0.1%  → ROE moves ±5%
  - Price moves 0.06% → ROE moves ±3%

This means a -5% ROE can be caused by a price move of only -0.1%.
That is NOISE. That is NOT a reason to CLOSE.

RULE: Do NOT use ROE or Unrealized PnL alone as evidence for CLOSE.
  → Focus on PRICE DISTANCE FROM ENTRY (shown in the status block) — that is the real market move.
  → A negative ROE that corresponds to a small price distance (< 0.20% from entry) is NORMAL VOLATILITY.
  → CLOSE decisions must be based on PRICE STRUCTURE, not leveraged PnL emotions.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ENTRY NOISE ZONE (CRITICAL)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
If ENTRY NOISE ZONE = TRUE (price is within ±0.15% of entry price):
  → This is NORMAL ENTRY ROTATION. Futures markets routinely sweep liquidity at entry before moving.
  → CLOSE is FORBIDDEN unless: SL is nearly hit OR 15m+ HTF structure is clearly invalidated.
  → Apply MAXIMUM HOLD BIAS. Do not be scared by leveraged PnL in this zone.
  → Micro breaks, delta flips, and ADX drops inside this zone are ALL NOISE.

Reason: limit/void/imbalance entries almost always experience initial rotation before the move begins.
Being shaken out of a valid setup during entry rotation is the most common avoidable loss.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOLD CONFIDENCE DECAY (TIME-BASED BIAS)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Position age determines your default HOLD strength:

  0–5 minutes:   MAXIMUM HOLD BIAS — almost nothing justifies CLOSE except SL nearly hit or 15m+ HTF break
  5–15 minutes:  STRONG HOLD BIAS — need clear HTF confirmation for CLOSE; LTF signals still insufficient
  15–60 minutes: NORMAL MONITORING — standard multi-confirmation rules apply for CLOSE
  60m+:          STRUCTURE FOCUS — HTF structure and thesis score are primary; can consider SL+ more freely

Reason: new trades are always the noisiest. Patience in the first 5–15 minutes protects the edge.
Over-evaluating a fresh entry leads to systematic overreaction. Most profitable systems trade LESS, not more.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SIGNAL HIERARCHY — WEIGHT SIGNALS CORRECTLY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TIER 1 — HARD TRUTH (these drive CLOSE decisions):
  • HTF structure break (15m/1H/4H higher_low or lower_high violated)
  • thesis_score (primary health indicator of the trade)
  • abnormal_move = true on 15m+ (price truly outside normal ATR range)

TIER 2 — CONTEXT (adds weight, never decides alone):
  • CVD divergence on 15m+ (sustained, not 1m flip)
  • ADX / momentum on 15m+
  • Session (Asia thin, NY/London expansion)

TIER 3 — NOISE (do not overweight these):
  • 1m / 3m delta flip
  • micro_break on 1m or 3m
  • Tiny reversal candles on LTF
  • ROE / Unrealized PnL (leverage-amplified)

You are a discretionary trader. Focus on 2–4 signals max. Combining too many Tier 3 signals
does NOT make a CLOSE — it just means the market is breathing normally.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MICRO REVERSALS ARE NORMAL — DO NOT PANIC
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Small timeframe reversals immediately after entry are EXPECTED market behavior.
Crypto futures markets routinely:
  • Sweep liquidity below/above entry before moving to target
  • Print fake breakouts on 1m/3m before reclaiming structure
  • Show delta flips on small timeframes during consolidation

Do NOT CLOSE because of:
  - A single micro_break on 1m or 3m
  - A temporary delta flip on 1m or 3m
  - One or two bearish/bullish impulse candles against the position
  - ADX dropping after entry (consolidation is normal)
  - Negative ROE when price is still close to entry (this is leverage amplification, not invalidation)
  - Price slightly below/above entry (still within normal retrace range)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOW TO USE BACKEND CONTEXT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VOLUME DELTA / CVD:
- Delta flips on 1m/3m are NORMAL and NOT a CLOSE signal by themselves.
- Only sustained CVD divergence on 15m+ is meaningful for CLOSE consideration.
- LONG: delta_last_5 strongly negative on 15m+ AND CVD diverging → early warning, consider SL+
- SHORT: buyer_pressure flipping bullish on 15m+ AND CVD rising → early warning, consider SL+
- Alone, volume delta is a WARNING signal, not a CLOSE trigger.

MOMENTUM (ADX):
- ADX dropping after entry is NORMAL — market consolidates before expanding.
- ADX weakening alone is NOT sufficient reason to CLOSE. Use as supporting context only.
- ADX > 25 on 15m+: trend still strong → HOLD
- ADX < 18 on 15m+ AND combined with structure break AND delta divergence → lean CLOSE

SWING STRUCTURE:
- micro_break = true on 1m/3m → this is NOISE on small TF → treat as WARNING only, NOT CLOSE
- micro_break = true on 15m+ → stronger signal → assess with other confirmations
- last_higher_low (LONG) or last_lower_high (SHORT) violated on 1H/4H → serious → lean CLOSE
- Structure breaks on small TFs (1m, 3m) MUST be confirmed on 15m or higher before CLOSE.

LIQUIDITY SWEEP:
- sweep_low_recovery on LONG → possible reversal or SL hunt → SL+ if in profit, or HOLD
- sweep_high_rejection on SHORT → SL hunt possible → SL+ if in profit, or HOLD
- Combined with 15m+ delta divergence → lean CLOSE

ATR PULLBACK NORMALIZATION (CRITICAL):
- current_pullback < atr_normal_pullback → NORMAL retrace → HOLD, not CLOSE
- abnormal_move = true on 15m+ → beyond normal volatility → consider CLOSE (still need HTF confirmation)
- abnormal_move = true on 1m/3m only → WARNING, not CLOSE
- NEVER close because of pullback if abnormal_move = false

SESSION AWARENESS:
- ASIA session: thin volume, fakeouts common — be extra patient with reversals
- NY_OPEN / LONDON: expansion phase — give more room, lean HOLD
- Session close / ASIA_PRE: if floating profit → consider SL+

THESIS SCORE (backend scoring):
- score >= 3: thesis mostly intact → HOLD
- score == 2: borderline → need other HTF confirmations before CLOSE
- score <= 1: thesis weakening → lean SL+ or CLOSE if confirmed on HTF
- structure_break = true on HTF (15m+) → strong signal for CLOSE
- momentum_shift = true → consider SL+ first, CLOSE only if HTF confirms

INVALIDATION vs VOLATILITY RULE:
- abnormal_move = false + thesis_score >= 2 → HOLD
- abnormal_move = false + thesis_score >= 3 → STRONG HOLD, no question
- Structure break only on 1m/3m → WARNING, still HOLD unless HTF also breaks
- Structure break on 15m+ + abnormal_move = true + delta diverging → consider CLOSE

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CLOSE DECISION — REQUIRES MULTIPLE CONFIRMATIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CLOSE requires at least 2 of the following 3 conditions, with at least one from the HTF tier:

HTF TIER (15m or higher timeframe signals):
  [A] HTF structure break — last_higher_low (LONG) or last_lower_high (SHORT) violated on 15m+
  [B] abnormal_move = true on 15m+ (price moved beyond normal ATR range)
  [C] thesis_score <= 1 (original entry thesis has mostly broken down)

SUPPORTING TIER (adds weight but not sufficient alone):
  [D] Sustained CVD divergence on 15m+ (not 1m/3m delta flip)
  [E] ADX < 18 on 15m+ AND candle velocity collapsed AND delta reversed
  [F] Liquidity sweep + delta divergence combined on 15m+

MINIMUM REQUIREMENT FOR CLOSE:
  → Need ([A] OR [B] OR [C]) AND at least one supporting signal from [D], [E], or [F]
  → OR: [A] + [B] together (two HTF confirmations) is sufficient alone
  → Single signal only → HOLD or SL+ at most

Do NOT CLOSE based on:
  - micro_break on 1m/3m alone
  - ADX weakening alone
  - Delta flip on 1m/3m alone
  - "Risk/reward no longer justifies holding" without concrete HTF invalidation
  - Price slightly against position (within ATR normal range)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SL+ (Move Stop Loss)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Use when the position is in PROFIT and you want to lock gains:
- Price has moved significantly in our favour
- Original thesis is still intact and TP is still the target
- Trail the SL closer to price to lock profit but NOT close yet
- Classic use cases:
  • Move SL toward break-even ONLY after price is clearly past TP1 and holding above it
  • Trail SL behind a recent swing low/high to lock partial gains
  • Liquidity sweep detected + floating profit → SL+
  • ASIA session thin volume + floating profit → SL+ to protect
- When choosing SL+, you MUST provide new_sl:
  • For LONG: new_sl must be ABOVE current SL but BELOW current price
  • For SHORT: new_sl must be BELOW current SL but ABOVE current price
- CRITICAL: new_sl must have at least 0.2% buffer below current price (LONG) or above (SHORT)
  → Moving SL too tight guarantees the next normal candle stops you out — that is NOT locking profit
- Do NOT use SL+ if position is at a loss — use HOLD instead.
- Do NOT move SL+ so tight that 1x ATR would immediately stop it out.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TP1 HIT — TRAILING LOGIC (REVISED)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
When TP1 has been reached and position is in profit, do NOT force SL+ to entry.
Moving SL to exact entry price = the next normal crypto retracement will stop you out immediately.
That is not locking profit — that is guaranteeing a loss from fees.

CORRECT behavior after TP1 hit:
→ Default: HOLD — let price run toward TP2. TP1 is the MINIMUM target, not the exit.
→ SL+ is OPTIONAL and only if price has clearly rejected from TP1 (strong reversal candle on 15m+)
→ If you do use SL+, set new_sl between entry and TP1 (NOT at entry):
   For LONG: new_sl = entry + (TP1 - entry) * 0.4   ← 40% of the TP1 distance above entry
   For SHORT: new_sl = entry - (entry - TP1) * 0.4   ← 40% of the TP1 distance below entry
   This gives a small buffer so normal volatility does NOT stop the position.
→ Only move SL to entry (break-even) after price has reached midpoint between TP1 and TP2.

NEVER: move SL to exact entry price right after TP1 is first touched.
REASON: In leveraged futures, price routinely returns to TP1 level before continuing to TP2.
A SL at exact entry will be triggered by this normal retracement, exiting a winning trade.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOLD DECISION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Use when (any of these):
- The original analysis thesis is still intact on HTF
- Price is in normal pullback/consolidation within trade direction
- abnormal_move = false (ATR context confirms this is normal retrace)
- thesis_score >= 2 and no HTF structure break
- TP is still reachable from current price structure
- Position was opened recently (< 15 min) and no HTF invalidation has occurred
- Only LTF (1m/3m) signals are against position, but HTF is still intact
- Signals are mixed or ambiguous — when in doubt, HOLD

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Respond with EXACTLY this JSON and nothing else:
  {"decision": "HOLD" or "CLOSE" or "SL+", "reason": "max 120 chars", "new_sl": <number or null>}
- "new_sl" is REQUIRED when decision is "SL+" — must be a number (the new stop-loss price)
- "new_sl" must be null for HOLD and CLOSE
- No markdown, no preamble, no extra text outside the JSON
- decision must be exactly "HOLD", "CLOSE", or "SL+"
"""


def _fmt_ts(ts_ms: Optional[int]) -> str:
    if not ts_ms:
        return "unknown"
    try:
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return str(ts_ms)


def _elapsed(opened_at_ms: Optional[int]) -> str:
    if not opened_at_ms:
        return "unknown"
    try:
        elapsed_s = int(time.time()) - int(opened_at_ms / 1000)
        if elapsed_s < 60:
            return f"{elapsed_s}s ago"
        elif elapsed_s < 3600:
            return f"{elapsed_s // 60}m {elapsed_s % 60}s ago"
        else:
            h = elapsed_s // 3600
            m = (elapsed_s % 3600) // 60
            return f"{h}h {m}m ago"
    except Exception:
        return "unknown"


class _ImageUploadFailed(Exception):
    """Raised internally saat 502 image_upload_failed — sinyal ke pool untuk rotate token."""
    pass


class PositionAIClient:
    def __init__(self, token: str, slot: int = 1):
        self.token = token
        self.slot = slot
        self.client = httpx.AsyncClient(timeout=180)
        self.exhausted = False  # True kalau kena rate limit harian

    async def _refresh(self) -> bool:
        """Token refresh not applicable with reverse API."""
        return False

    async def decide(
        self,
        symbol: str,
        direction: str,
        entry: float,
        tp: float,
        sl: float,
        current_price: float,
        candles_by_tf: dict,
        leverage: int,
        margin_usdt: float,
        original_analysis: dict = None,
        opened_at: Optional[int] = None,
        original_prompt: Optional[str] = None,
        original_ai_response: Optional[str] = None,
        sl_plus_history: Optional[list] = None,
        tp1: float = None,
        position_context: dict = None,
        trade_chat_id: Optional[str] = None,
        trade_token: Optional[str] = None,
    ) -> Optional[dict]:
        if direction == "LONG":
            pnl_pct = round((current_price - entry) / entry * 100, 3)
            pct_to_tp = round((tp - current_price) / current_price * 100, 3)
            pct_to_sl = round((current_price - sl) / current_price * 100, 3)
        else:
            pnl_pct = round((entry - current_price) / entry * 100, 3)
            pct_to_tp = round((current_price - tp) / current_price * 100, 3)
            pct_to_sl = round((sl - current_price) / current_price * 100, 3)

        pnl_usdt = round(margin_usdt * leverage * pnl_pct / 100, 4)
        sign = "+" if pnl_pct >= 0 else ""
        pnl_icon = "🟢" if pnl_pct >= 0 else "🔴"

        # ── Price distance from entry (real market move, not leverage-amplified) ──
        price_distance_pct = round((current_price - entry) / entry * 100, 4)  # signed, no leverage
        price_distance_abs = abs(price_distance_pct)
        entry_noise_zone = price_distance_abs < 0.15  # within ±0.15% = normal entry rotation
        price_dist_sign = "+" if price_distance_pct >= 0 else ""
        price_dist_icon = "🟢" if price_distance_pct >= 0 else "🔴"

        # ── Position age in minutes ───────────────────────────────────────────────
        position_age_min: float = 0.0
        if opened_at:
            try:
                position_age_min = (time.time() - opened_at / 1000) / 60
            except Exception:
                position_age_min = 0.0

        if position_age_min < 5:
            age_bias = "MAXIMUM HOLD BIAS (< 5 min — highest noise window)"
        elif position_age_min < 15:
            age_bias = "STRONG HOLD BIAS (5–15 min — still early, LTF noise expected)"
        elif position_age_min < 60:
            age_bias = "NORMAL MONITORING (15–60 min — standard rules apply)"
        else:
            age_bias = "STRUCTURE FOCUS (60m+ — HTF structure and thesis are primary)"

        # ── Check TP1 hit condition ──────────────────────────────────
        tp1_hit = False
        if tp1 is not None and tp1 > 0:
            if direction == "LONG" and current_price >= tp1:
                tp1_hit = True
            elif direction == "SHORT" and current_price <= tp1:
                tp1_hit = True

        # ── Build time context block ───────────────────────────────────
        opened_str = _fmt_ts(opened_at)
        elapsed_str = _elapsed(opened_at)
        time_block = (
            f"\n━━━ POSITION TIMING ━━━\n"
            f" Opened At: {opened_str}\n"
            f" Time Elapsed: {elapsed_str}\n"
            f" Current Time: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # ── Build original analysis block ──────────────────────────────
        orig_block = ""
        if original_analysis:
            orig_trend = original_analysis.get("trend", "N/A")
            orig_pat = original_analysis.get("pattern", "N/A")
            orig_reason = original_analysis.get("reason", "N/A")
            orig_conf = original_analysis.get("confidence", "N/A")
            orig_block = (
                f"\n━━━ ORIGINAL OPEN ANALYSIS (structured) ━━━\n"
                f" Trend: {orig_trend}\n"
                f" Pattern: {orig_pat}\n"
                f" Confidence: {orig_conf}%\n"
                f" Reason: {orig_reason}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            )

        # ── Build SL+ history block ────────────────────────────────────
        sl_plus_block = ""
        if sl_plus_history:
            lines = ["\n━━━ SL+ HISTORY (previous stop-loss moves by YOU) ━━━"]
            original_sl = None
            for i, move in enumerate(sl_plus_history):
                frm = move.get("from")
                to = move.get("to")
                px = move.get("price")
                at_ms = move.get("at")
                at_str = _fmt_ts(at_ms) if at_ms else "unknown"
                if i == 0:
                    original_sl = frm
                lines.append(f" Move #{i+1}: SL {frm} → {to} (price was {px} at {at_str})")
            lines.append(f" Original SL: {original_sl} Current SL (after all moves): {sl}")
            lines.append(
                " NOTE: The current Stop Loss shown below already reflects these moves.\n"
                " If you choose SL+ again, provide a new_sl that is BETTER than the current SL.\n"
                " Do NOT move SL back toward the original — only tighten further or stay put."
            )
            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
            sl_plus_block = "\n".join(lines)

        # ── Build backend position context block ──────────────────────
        pctx_block = ""
        pc = position_context or {}
        if pc:
            session = pc.get("session", "UNKNOWN")
            thesis = pc.get("thesis_score", {})
            atr_ctx = pc.get("atr_context", {})
            vd = pc.get("volume_delta", {})
            momentum = pc.get("momentum", {})
            swing_str = pc.get("swing_structure", {})
            liq_sweep = pc.get("liquidity_sweep", {})

            thesis_lines = (
                f"  trend_intact={thesis.get('trend_intact')} | "
                f"volume_support={thesis.get('volume_support')} | "
                f"momentum_shift={thesis.get('momentum_shift')} | "
                f"structure_break={thesis.get('structure_break')} | "
                f"score={thesis.get('score')}/4"
            ) if thesis else "  N/A"

            atr_lines = "\n".join(
                f"  {tf}: atr={v.get('atr')} normal_pullback={v.get('atr_normal_pullback')} "
                f"current_pullback={v.get('current_pullback')} abnormal={v.get('abnormal_move')}"
                for tf, v in atr_ctx.items()
            ) if atr_ctx else "  N/A"

            vd_lines = "\n".join(
                f"  {tf}: cvd={v.get('cvd_last_20')} delta5={v.get('delta_last_5')} pressure={v.get('buyer_pressure')}"
                for tf, v in vd.items()
            ) if vd else "  N/A"

            mom_lines = "\n".join(
                f"  {tf}: adx={v.get('adx')} strength={v.get('trend_strength')} velocity={v.get('candle_velocity')}"
                for tf, v in momentum.items()
            ) if momentum else "  N/A"

            swing_lines = "\n".join(
                f"  {tf}: structure={v.get('structure')} micro_break={v.get('micro_break')} "
                f"HH={v.get('last_hh')} HL={v.get('last_hl')} LH={v.get('last_lh')} LL={v.get('last_ll')}"
                for tf, v in swing_str.items()
            ) if swing_str else "  N/A"

            sweep_lines = "\n".join(
                f"  {tf}: detected={v.get('detected')} type={v.get('type')}"
                for tf, v in liq_sweep.items()
                if v.get("detected")
            ) or "  None detected"

            pctx_block = (
                f"\n━━━ BACKEND POSITION CONTEXT (USE THIS FOR DECISION) ━━━\n"
                f" Session: {session}\n"
                f"\n Thesis Score:\n{thesis_lines}\n"
                f"\n ATR Pullback Normalization:\n{atr_lines}\n"
                f"\n Volume Delta / CVD:\n{vd_lines}\n"
                f"\n Momentum (ADX):\n{mom_lines}\n"
                f"\n Swing Structure:\n{swing_lines}\n"
                f"\n Liquidity Sweeps:\n{sweep_lines}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            )

        # ── Build OHLCV blocks ─────────────────────────────────────────
        ohlcv_blocks = []
        for tf, candles in candles_by_tf.items():
            recent = candles[-80:]
            lines = [f"=== {symbol} | {tf} | {len(recent)} candles ===",
                     "timestamp, open, high, low, close, volume"]
            for c in recent:
                lines.append(f"{c[0]}, {c[1]}, {c[2]}, {c[3]}, {c[4]}, {c[5]}")
            ohlcv_blocks.append("\n".join(lines))

        noise_zone_line = (
            f" ⚠️  ENTRY NOISE ZONE: YES — price within ±0.15% of entry → MAXIMUM HOLD BIAS, do NOT close\n"
            if entry_noise_zone else
            f" ENTRY NOISE ZONE: NO — price has moved beyond ±0.15% from entry\n"
        )

        user_text = (
            f"ACTIVE POSITION — HOLD, CLOSE, or SL+?\n"
            f"{time_block}"
            f"{orig_block}"
            f"{sl_plus_block}"
            f"━━━ CURRENT POSITION STATUS ━━━\n"
            f" Symbol: {symbol}\n"
            f" Direction: {direction}\n"
            f" Entry: {entry}\n"
            f" Current Price: {current_price}\n"
            f"\n"
            f" ── REAL MARKET MOVE (not leverage-amplified) ──\n"
            f" {price_dist_icon} Price Distance from Entry: {price_dist_sign}{price_distance_pct}%\n"
            f"   → Actual price moved {price_dist_sign}{price_distance_pct}% from entry\n"
            f"{noise_zone_line}"
            f"\n"
            f" ── LEVERAGED PnL (for reference only — NOT a trade decision signal) ──\n"
            f" {pnl_icon} Unrealized ROE: {sign}{pnl_pct}% ({sign}{pnl_usdt} USDT) [{leverage}x leverage]\n"
            f"   ⚠ ROE amplifies real price move by {leverage}x. Do NOT use ROE alone to justify CLOSE.\n"
            f"\n"
            f" Take Profit: {tp} ({pct_to_tp:+.3f}% away)\n"
            f" Stop Loss: {sl} (-{pct_to_sl:.3f}% away)\n"
            f" TP1 Level: {tp1 if tp1 else 'N/A'}\n"
            f" TP1 Hit: {'YES ✅' if tp1_hit else 'NO'}\n"
            f" Leverage: {leverage}x | Margin: {margin_usdt} USDT\n"
            f"\n"
            f" ── HOLD BIAS (based on position age) ──\n"
            f" ⏱ Position Age: {elapsed_str} ({position_age_min:.1f} min)\n"
            f" 🎯 Current Bias: {age_bias}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{pctx_block}"
            f"{chr(10).join(ohlcv_blocks)}\n\n"
            f"Charts attached above.\n"
            f"Remember: this position was opened {elapsed_str}. "
            f"Judge whether the ORIGINAL HTF THESIS is still valid — focus on PRICE STRUCTURE, not ROE.\n"
            f"PRICE DISTANCE from entry = {price_dist_sign}{price_distance_pct}% (real move). "
            f"ROE = {sign}{pnl_pct}% (leverage-amplified, treat as noise unless price has truly moved).\n"
            f"LTF (1m/3m) noise, micro_break, or delta flip alone is NOT enough to CLOSE.\n"
            f"CLOSE requires multiple HTF confirmations. DEFAULT = HOLD. When in doubt → HOLD.\n"
            f"If TP1 has been HIT and position is in PROFIT → HOLD and let price run to TP2. "
            f"Only use SL+ if price has clearly rejected TP1 on 15m+, and set new_sl with buffer (NOT at entry).\n"
            f'Respond ONLY with JSON: {{"decision": "HOLD"|"CLOSE"|"SL+", "reason": "brief reason", "new_sl": <number or null>}}\n'
            f'For SL+: provide new_sl as a number (new stop-loss price). For HOLD/CLOSE: new_sl must be null.'
        )

        # Upload chart images to OSS
        uploaded_files = []
        if HAS_CHARTS:
            for tf, candles in candles_by_tf.items():
                img = _draw_chart(candles, symbol, tf)
                if img:
                    uf = await _upload_image_bytes(
                        self.token, base64.b64decode(img),
                        f"pos_{symbol}_{tf}.png", "image/png", self.client,
                    )
                    if uf:
                        uploaded_files.append(uf)

        # ── Build prompt for this message ─────────────────────────────
        # First message: system prompt + original analysis + current status
        # Subsequent messages: just the current status update (context is in history)
        is_first_message = (trade_chat_id is None)
        # Token yang dipakai: kalau room sudah ada, HARUS pakai token yang sama
        # dengan yang buat room itu (trade_token). Kalau buat room baru, pakai self.token.
        effective_token = self.token if is_first_message else (trade_token or self.token)

        if is_first_message:
            # Build initial context block with original analysis
            analysis_block = ""
            if original_prompt or original_ai_response:
                parts = ["\n━━━ ORIGINAL ANALYSIS (why this trade was opened) ━━━"]
                if original_prompt:
                    preview = original_prompt[:3000] + ("\n... [truncated]" if len(original_prompt) > 3000 else "")
                    parts.append(f"\n[ANALYSIS AI PROMPT]\n{preview}")
                if original_ai_response:
                    preview = original_ai_response[:3000] + ("\n... [truncated]" if len(original_ai_response) > 3000 else "")
                    parts.append(f"\n[ANALYSIS AI RESPONSE]\n{preview}")
                parts.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
                analysis_block = "\n".join(parts)

            system = POSITION_SYSTEM_PROMPT.format(monitor_interval=MONITOR_INTERVAL)
            message_to_send = (
                f"{system}\n\n"
                f"━━━ TRADE ROOM OPENED ━━━\n"
                f"Symbol: {symbol} | Direction: {direction} | Entry: {entry}\n"
                f"Leverage: {leverage}x | Margin: {margin_usdt} USDT\n"
                f"TP: {tp} | SL: {sl} | TP1: {tp1 if tp1 else 'N/A'}\n"
                f"You will receive position updates every {MONITOR_INTERVAL} seconds in this room.\n"
                f"{analysis_block}\n"
                f"━━━ INITIAL POSITION STATUS ━━━\n"
                f"{user_text}"
            )
        else:
            # Subsequent updates — context already in chat history
            message_to_send = (
                f"━━━ POSITION UPDATE (+{MONITOR_INTERVAL}s) ━━━\n"
                f"{user_text}"
            )

        full_text = ""
        returned_chat_id = trade_chat_id
        lock = ai_lock()
        print(f"[PositionAI] waiting for lock ({symbol} {direction} pnl={sign}{pnl_pct}% elapsed={elapsed_str})")
        async with lock:
            print(f"[PositionAI] lock acquired → {'opening trade room' if is_first_message else 'update'} for {symbol}")
            for attempt in range(2):
                try:
                    if is_first_message:
                        # Create room and send first message
                        chat_id = await _create_chat(effective_token, self.client)
                        if not chat_id:
                            if attempt == 0:
                                continue
                            return None
                        returned_chat_id = chat_id
                        print(f"[PositionAI] trade room created: {chat_id} for {symbol}")
                    else:
                        chat_id = trade_chat_id

                    raw_reply = await _send_stream(
                        effective_token, chat_id, message_to_send, self.client, uploaded_files or None
                    )
                    # Do NOT delete — room persists until trade closes

                    if raw_reply:
                        import re
                        full_text = re.sub(r"<think>.*?</think>", "", raw_reply, flags=re.DOTALL).strip()
                        break

                    if attempt == 0:
                        continue
                    return None
                except httpx.TimeoutException:
                    print(f"[PositionAI] timeout for {symbol} — will retry")
                    return None
                except Exception as e:
                    logger.error(f"[PositionAI] {e}")
                    return None

        print(f"[PositionAI] raw [{symbol}]: {full_text[:200]}")
        if not full_text.strip():
            return None

        start = full_text.find("{")
        end = full_text.rfind("}") + 1
        if start < 0 or end <= start:
            return None

        try:
            result = json.loads(full_text[start:end])
        except json.JSONDecodeError:
            return None

        decision = str(result.get("decision", "")).upper().strip()
        if decision in ("SL +", "SL_PLUS", "SLPLUS", "SL PLUS"):
            decision = "SL+"
        if decision not in ("HOLD", "CLOSE", "SL+"):
            logger.warning(f"[PositionAI] invalid decision '{decision}' for {symbol}")
            return None

        reason = str(result.get("reason", ""))[:200]

        # Extract and validate new_sl for SL+ decisions
        new_sl = None
        if decision == "SL+":
            raw_sl = result.get("new_sl")
            try:
                new_sl = float(raw_sl)
                if new_sl <= 0:
                    logger.warning(f"[PositionAI] SL+ new_sl={raw_sl} invalid (≤0) — downgrading to HOLD")
                    return {"decision": "HOLD", "reason": "SL+ had invalid new_sl, holding instead"}
                if direction == "LONG" and new_sl >= current_price:
                    logger.warning(f"[PositionAI] SL+ new_sl={new_sl} >= price={current_price} for LONG — rejected")
                    return {"decision": "HOLD", "reason": "SL+ new_sl above price for LONG, holding instead"}
                if direction == "SHORT" and new_sl <= current_price:
                    logger.warning(f"[PositionAI] SL+ new_sl={new_sl} <= price={current_price} for SHORT — rejected")
                    return {"decision": "HOLD", "reason": "SL+ new_sl below price for SHORT, holding instead"}
            except (TypeError, ValueError):
                logger.warning(f"[PositionAI] SL+ missing/invalid new_sl={raw_sl!r} — downgrading to HOLD")
                return {"decision": "HOLD", "reason": "SL+ had no valid new_sl, holding instead"}

        print(f"[PositionAI] {symbol} → {decision} | {reason}" + (f" | new_sl={new_sl}" if new_sl else ""))
        return {
            "decision": decision,
            "reason": reason,
            "new_sl": new_sl,
            "chat_id": returned_chat_id,
            "chat_token": effective_token,   # token pemilik room ini
        }

    async def close(self):
        await self.client.aclose()


class PositionMonitorAI:
    def __init__(self):
        self._clients: list[PositionAIClient] = []
        self._current_idx: int = 0
        self._reload_tokens()

    def _reload_tokens(self):
        """Buat/update client pool dari token list terbaru."""
        old_clients = self._clients
        self._clients = [
            PositionAIClient(token=t, slot=i + 1)
            for i, t in enumerate(_load_monitor_tokens())
        ]
        # Tutup client lama
        for c in old_clients:
            asyncio.create_task(c.close()) if asyncio.get_event_loop().is_running() else None
        self._current_idx = 0
        print(f"[PositionAI] Pool ready: {len(self._clients)} token(s)")

    @property
    def enabled(self) -> bool:
        return len(self._clients) > 0

    def _next_client(self) -> Optional["PositionAIClient"]:
        """Round-robin: lewati token yang exhausted."""
        total = len(self._clients)
        if not total:
            return None
        for _ in range(total):
            client = self._clients[self._current_idx % total]
            self._current_idx = (self._current_idx + 1) % total
            if not client.exhausted:
                return client
        return None  # semua exhausted

    async def decide_with_retry(
        self,
        symbol: str,
        direction: str,
        entry: float,
        tp: float,
        sl: float,
        current_price: float,
        candles_by_tf: dict,
        leverage: int,
        margin_usdt: float,
        original_analysis: dict = None,
        opened_at: Optional[int] = None,
        original_prompt: Optional[str] = None,
        original_ai_response: Optional[str] = None,
        sl_plus_history: Optional[list] = None,
        tp1: float = None,
        position_context: dict = None,
        trade_chat_id: Optional[str] = None,
        trade_token: Optional[str] = None,
        max_retries: int = 999,
    ) -> dict:
        """
        Retry sampai dapat HOLD/CLOSE/SL+.
        - Saat image_upload_failed → rotate ke token berikutnya (tidak tunggu)
        - Saat exhausted → skip token, coba yang lain
        - Backoff 10s → 30s untuk error lain
        """
        if not self._clients:
            return {"decision": "HOLD", "reason": "No token configured"}

        image_fail_slots: set[int] = set()  # track slot yang gagal image di round ini

        for attempt in range(max_retries):
            client = self._next_client()
            if client is None:
                print(f"[PositionAI] All tokens exhausted — HOLD {symbol}")
                return {"decision": "HOLD", "reason": "All tokens exhausted — holding position"}

            try:
                result = await client.decide(
                    symbol=symbol,
                    direction=direction,
                    entry=entry,
                    tp=tp,
                    sl=sl,
                    current_price=current_price,
                    candles_by_tf=candles_by_tf,
                    leverage=leverage,
                    margin_usdt=margin_usdt,
                    original_analysis=original_analysis,
                    opened_at=opened_at,
                    original_prompt=original_prompt,
                    original_ai_response=original_ai_response,
                    sl_plus_history=sl_plus_history,
                    tp1=tp1,
                    position_context=position_context,
                    trade_chat_id=trade_chat_id,
                    trade_token=trade_token,
                )
            except _ImageUploadFailed:
                # Token ini gagal upload image — langsung rotate, tanpa sleep
                image_fail_slots.add(client.slot)
                print(
                    f"[PositionAI] ↻ Image fail slot={client.slot} — rotating to next token "
                    f"(failed slots this round: {image_fail_slots})"
                )
                # Kalau semua token sudah gagal image → retry dengan delay
                if len(image_fail_slots) >= len(self._clients):
                    image_fail_slots.clear()
                    wait = min(10 * (attempt + 1), 30)
                    print(f"[PositionAI] All tokens failed image for {symbol} — wait {wait}s before retry")
                    await asyncio.sleep(wait)
                continue  # langsung coba token berikutnya

            if result and result.get("decision") in ("HOLD", "CLOSE", "SL+"):
                return result

            wait = min(10 * (attempt + 1), 30)
            print(f"[PositionAI] no valid response for {symbol} — retry {attempt+1} in {wait}s")
            await asyncio.sleep(wait)

        return {"decision": "HOLD", "reason": "Retries exhausted"}

    def reset_exhausted(self):
        """Reset exhausted flag semua token — dipanggil saat token di-update via admin route."""
        for c in self._clients:
            c.exhausted = False
        print(f"[PositionAI] Exhausted flags reset for {len(self._clients)} token(s)")

    def reload_tokens(self):
        """Hot-reload token pool (dipanggil dari admin route setelah update token)."""
        self._reload_tokens()

    async def close(self):
        for c in self._clients:
            await c.close()


position_ai = PositionMonitorAI()
