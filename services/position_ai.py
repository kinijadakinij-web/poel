"""
Position Monitor AI — HOLD or CLOSE untuk posisi yang sudah entry.

Features:
 • Multi-token pool (MONITOR_TOKEN_1..5, fallback ke QWEN_TOKEN_1..5 via token_manager)
 • Token rotation saat image_upload_failed — langsung coba token berikutnya
 • Pakai ai_lock() agar tidak bentrok dengan analysis AI
 • Retry terus sampai dapat HOLD/CLOSE/SL+ yang valid
 • Menyertakan opened_at, original_prompt, dan original_ai_response
 • SL+ enhanced: trigger SL+ ketika TP1 sudah tercapai dan PnL positif
 • ENTRY NOISE ZONE + HOLD CONFIDENCE DECAY — mencegah close premature
 • Signal hierarchy (Tier1/2/3) agar tidak overloaded noise

Env vars:
 MONITOR_TOKEN_1..5 — bearer token khusus monitor (opsional)
 (kalau tidak diset, fallback ke QWEN_TOKEN_1..5 dari token_manager)
 MONITOR_INTERVAL_SECONDS — seberapa sering query per posisi (default: 120s)
 ENTRY_NOISE_ZONE_PCT — batas persen harga dari entry yang dianggap noise (default 0.15)
 MIN_HOLD_TIME_SECONDS — waktu minimal sebelum boleh close (default 300 = 5 menit)
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

# Entry noise zone (% dari entry price). Harga bergerak dalam zone ini dianggap normal.
ENTRY_NOISE_ZONE_PCT = float(os.getenv("ENTRY_NOISE_ZONE_PCT", "0.15"))  # 0.15%
MIN_HOLD_TIME_SECONDS = int(os.getenv("MIN_HOLD_TIME_SECONDS", "300"))     # 5 menit


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
# System prompt — position management with improved patience, noise zone, hierarchy
# ---------------------------------------------------------------------------
POSITION_SYSTEM_PROMPT = """You are a position management AI for a crypto futures trading bot.

AN ACTIVE OPEN POSITION is running — entry price has already been hit.
You will receive:
 1. When the position was opened (OPENED AT)
 2. The exact prompt the analysis AI received when it decided to enter this trade
 3. The analysis AI's full response that justified the entry
 4. The current position status and latest candle data
 5. Backend pre-computed context

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DEFAULT BEHAVIOR — READ THIS FIRST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOLD is ALWAYS the default decision.
CLOSE is the exception — it requires MULTIPLE strong confirmations, not just one signal.
When in doubt between HOLD and CLOSE → choose HOLD.
Early patience protects the edge. Premature exits destroy it.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ENTRY NOISE ZONE (CRITICAL NEW RULE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
If current price is within ±{ENTRY_NOISE_ZONE_PCT}% of entry price, this is considered
NORMAL ENTRY ROTATION. In this zone:
  → DO NOT CLOSE unless there is a CLEAR HTF structural invalidation
  → DO NOT use small negative PnL, delta flips, or micro breaks as close signals
  → HOLD is mandatory unless structural invalidation confirmed on 15m or higher timeframe

Crypto futures often rotate, sweep liquidity, then move. Noise zone is not invalidation.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
UNREALIZED PNL / ROE IS NOT STRUCTURAL INVALIDATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
High leverage (50x) amplifies normal price movement.
A small negative ROE (-5%) may represent a price move of only -0.1%.
DO NOT use ROE/PnL alone as evidence for CLOSE.
Focus on PRICE STRUCTURE and DISTANCE FROM ENTRY, not leverage-amplified PnL.

If price is within noise zone, ignore PnL color completely.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOLD CONFIDENCE DECAY (TIME-BASED RULE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 0 – 5 minutes: VERY STRONG HOLD bias. CLOSE not allowed unless:
    * SL level nearly hit (within 0.3%)
    * abnormal_move = true on 15m+ timeframe
    * HTF structure clearly broken on 15m or higher
- 5 – 15 minutes: normal HOLD bias. Still need multiple HTF confirmations to CLOSE.
- 15+ minutes: structure monitoring increases, but still need Tier1 confirmations.

The first minutes after entry are the highest-noise window. Be patient.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SIGNAL HIERARCHY (PREVENT NOISE OVERLOAD)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TIER 1 — Hard Truth (sufficient alone to consider CLOSE if multiple)
  [A] HTF structure break (15m+ last_higher_low or last_lower_high violated)
  [B] abnormal_move = true on 15m+ (price moved beyond normal ATR range)
  [C] thesis_score <= 1 (original entry thesis has mostly broken down)

TIER 2 — Context (adds weight but not sufficient alone)
  [D] Sustained CVD divergence on 15m+ (not 1m/3m delta flip)
  [E] ADX < 18 on 15m+ AND candle velocity collapsed AND delta reversed
  [F] Liquidity sweep + delta divergence combined on 15m+

TIER 3 — Noise (ignore for CLOSE unless confirmed by Tier1/2)
  - 1m/3m micro_break
  - 1m/3m delta flip
  - Single bearish/bullish impulse candle
  - ADX dropping within 5 minutes after entry

CLOSE requires: ([A] OR [B] OR [C]) AND at least one from Tier2.
OR: [A] + [B] together is sufficient.

If only Tier3 signals present → HOLD.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SL+ (Move Stop Loss)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Use when the position is in PROFIT and you want to lock gains:
- Price has moved significantly in our favour
- Original thesis is still intact and TP is still the target
- Trail the SL closer to price to lock profit but NOT close yet
- Classic use cases:
  • Move SL to break-even once trade is in profit
  • Trail SL behind a recent swing low/high to lock partial gains
  • Liquidity sweep detected + floating profit → SL+
  • TP1 hit + thesis intact → SL+
  • ASIA session thin volume + floating profit → SL+ to protect
- When choosing SL+, you MUST provide new_sl:
  • For LONG: new_sl must be ABOVE current SL but BELOW current price
  • For SHORT: new_sl must be BELOW current SL but ABOVE current price
- Do NOT use SL+ if position is at a loss — use HOLD instead.
- Do NOT move SL+ so tight that 1x ATR would immediately stop it out.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TP1 HIT → FORCE SL+
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SPECIAL RULE: If ALL of the following are true, you MUST return SL+ (not HOLD):
1. TP1 level has been reached or exceeded by current price
2. Position is in PROFIT (PnL > 0)
3. Original thesis is still valid
→ Move SL to at least breakeven (entry price) or slightly better.
→ Set new_sl = entry price (or slightly better if already well in profit).
→ Reason: "TP1 hit + profit — locking gains with SL+"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOLD DECISION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Use when (any of these):
- The original analysis thesis is still intact on HTF
- Price is within noise zone or normal pullback/consolidation within trade direction
- abnormal_move = false (ATR context confirms this is normal retrace)
- thesis_score >= 2 and no HTF structure break
- TP is still reachable from current price structure
- Position age < 5 minutes (unless HTF break or abnormal move)
- Only Tier3 signals are against position, but HTF is still intact
- When in doubt → HOLD

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Respond with EXACTLY this JSON and nothing else:
  {{"decision": "HOLD" or "CLOSE" or "SL+", "reason": "max 120 chars", "new_sl": <number or null>}}
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
    ) -> Optional[dict]:
        # Hitung price distance from entry (real market move, bukan leverage amplified)
        price_distance_pct = round((current_price - entry) / entry * 100, 4) if entry > 0 else 0.0
        abs_distance_pct = abs(price_distance_pct)

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
        elapsed_seconds = int(time.time() - (opened_at / 1000)) if opened_at else 999999
        is_young = elapsed_seconds < MIN_HOLD_TIME_SECONDS

        time_block = (
            f"\n━━━ POSITION TIMING ━━━\n"
            f" Opened At: {opened_str}\n"
            f" Time Elapsed: {elapsed_str}\n"
            f" Current Time: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f" Is young (< {MIN_HOLD_TIME_SECONDS}s): {'YES (strong HOLD bias)' if is_young else 'NO'}\n"
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

        # ── Build original prompt/response block ───────────────────────
        conversation_block = ""
        if original_prompt or original_ai_response:
            parts = ["\n━━━ ORIGINAL ANALYSIS CONVERSATION ━━━"]
            if original_prompt:
                prompt_preview = original_prompt[:2000]
                if len(original_prompt) > 2000:
                    prompt_preview += "\n... [truncated]"
                parts.append(f"\n[MY PROMPT TO ANALYSIS AI]\n{prompt_preview}")
            if original_ai_response:
                response_preview = original_ai_response[:2000]
                if len(original_ai_response) > 2000:
                    response_preview += "\n... [truncated]"
                parts.append(f"\n[ANALYSIS AI RESPONSE]\n{response_preview}")
            parts.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
            conversation_block = "\n".join(parts)

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

        # Tampilkan price distance (real market move) lebih menonjol, PnL sebagai secondary
        user_text = (
            f"ACTIVE POSITION — HOLD, CLOSE, or SL+?\n"
            f"{time_block}"
            f"{orig_block}"
            f"{conversation_block}\n"
            f"{sl_plus_block}"
            f"━━━ CURRENT POSITION STATUS ━━━\n"
            f" Symbol: {symbol}\n"
            f" Direction: {direction}\n"
            f" Entry: {entry}\n"
            f" Current Price: {current_price}\n"
            f" PRICE DISTANCE FROM ENTRY: {price_distance_pct:+.4f}%  ← REAL MARKET MOVE (leverage not applied)\n"
            f" (Noise zone threshold = ±{ENTRY_NOISE_ZONE_PCT}% — within this zone = normal rotation)\n"
            f" Take Profit: {tp} ({pct_to_tp:+.3f}% away)\n"
            f" Stop Loss: {sl} (-{pct_to_sl:.3f}% away)\n"
            f" TP1 Level: {tp1 if tp1 else 'N/A'}\n"
            f" TP1 Hit: {'YES ✅' if tp1_hit else 'NO'}\n"
            f" {pnl_icon} Unrealized PnL (leveraged): {sign}{pnl_pct}% ({sign}{pnl_usdt} USDT) — this is AMPLIFIED by {leverage}x, not raw price move\n"
            f" Leverage: {leverage}x\n"
            f" Margin Used: {margin_usdt} USDT\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{pctx_block}"
            f"{chr(10).join(ohlcv_blocks)}\n\n"
            f"Charts attached above.\n"
            f"Remember: this position was opened {elapsed_str}. "
            f"Judge whether the ORIGINAL HTF THESIS is still valid — NOT just current price.\n"
            f"If price distance is within {ENTRY_NOISE_ZONE_PCT}%, you are in ENTRY NOISE ZONE → STRONG HOLD bias.\n"
            f"LTF (1m/3m) noise, micro_break, or delta flip alone is NOT enough to CLOSE.\n"
            f"CLOSE requires multiple HTF confirmations (Tier1+). DEFAULT = HOLD. When in doubt → HOLD.\n"
            f"If TP1 has been HIT and position is in PROFIT → return SL+ to lock gains.\n"
            f'Respond ONLY with JSON: {{"decision": "HOLD"|"CLOSE"|"SL+", "reason": "brief reason", "new_sl": <number or null>}}\n'
            f'For SL+: provide new_sl as a number (new stop-loss price). For HOLD/CLOSE: new_sl must be null.'
        )

        # Inject noise zone pct ke system prompt (dinamis)
        dynamic_system_prompt = POSITION_SYSTEM_PROMPT.format(ENTRY_NOISE_ZONE_PCT=ENTRY_NOISE_ZONE_PCT)

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

        full_prompt = dynamic_system_prompt + "\n\n---\n\n" + user_text

        full_text = ""
        lock = ai_lock()
        print(f"[PositionAI] waiting for lock ({symbol} {direction} pnl={sign}{pnl_pct}% elapsed={elapsed_str})")
        async with lock:
            print(f"[PositionAI] lock acquired → hold/close query for {symbol}")
            for attempt in range(2):
                try:
                    chat_id = await _create_chat(self.token, self.client)
                    if not chat_id:
                        if attempt == 0:
                            continue
                        return None

                    raw_reply = await _send_stream(
                        self.token, chat_id, full_prompt, self.client, uploaded_files or None
                    )
                    await _delete_chat(self.token, chat_id, self.client)

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
        return {"decision": decision, "reason": reason, "new_sl": new_sl}

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
