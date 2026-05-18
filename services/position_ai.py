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
    CHAT_URL,
    REFRESH_URL,
    QWEN_MODEL,
    QWEN_THINKING,
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

An ACTIVE OPEN POSITION is running — entry price has already been hit.
You will receive:
 1. When the position was opened (OPENED AT)
 2. The exact prompt the analysis AI received when it decided to enter this trade
 3. The analysis AI's full response that justified the entry
 4. The current position status and latest candle data

CRITICAL TIME AWARENESS:
- "OPENED AT" tells you how long this trade has been running.
- If the position was opened very recently (seconds to a few minutes ago), be VERY RELUCTANT to
  CLOSE based solely on price movement away from entry — the trade has barely started.
- The analysis AI's original prompt + response is the ground truth for WHY this trade was entered.
  Your job is to judge whether that thesis is STILL VALID, not whether the current price looks scary.
- Price naturally moves against a new position briefly before reaching TP — do NOT mistake normal
  volatility for thesis invalidation.

You have THREE possible decisions:

━━━ CLOSE ━━━
Use when:
- The original thesis (trend/pattern/void/structure) has been clearly invalidated by NEW candle data
- Clear reversal structure has formed AFTER entry (lower low for LONG / higher high for SHORT)
- The specific pattern or level cited in the original analysis has broken
- Momentum has definitively shifted with no recovery sign over multiple candles
- Risk/reward no longer justifies holding — better a small loss now than full SL

━━━ SL+ (Move Stop Loss) ━━━
Use when the position is in PROFIT and you want to lock in gains or protect break-even:
- Price has moved significantly in our favour
- The original thesis is still intact and TP is still the target
- You want to trail the SL closer to current price to lock profit but NOT close yet
- Classic use cases:
  • Move SL to break-even (entry price) once trade is in profit
  • Trail SL behind a recent swing low/high to lock partial gains
- When choosing SL+, you MUST provide a new_sl price:
  • For LONG: new_sl must be ABOVE the current SL but BELOW current price (never above entry is fine too)
  • For SHORT: new_sl must be BELOW the current SL but ABOVE current price
- Do NOT use SL+ if the position is still at a loss — use HOLD or CLOSE instead.
- Do NOT move SL+ so tight that normal volatility would immediately stop it out.

━━━ TP1 HIT → FORCE SL+ ━━━
SPECIAL RULE: If ALL of the following are true, you MUST return SL+ (not HOLD):
1. TP1 level has been reached or exceeded by current price
2. Position is in PROFIT (PnL > 0)
3. Original thesis is still valid
→ This is a "lock profits" scenario. Move SL to at least breakeven (entry price) or slightly better.
→ Set new_sl = entry price (or slightly better if already well in profit).
→ Reason: "TP1 hit + profit — locking gains with SL+"

━━━ HOLD ━━━
Use when:
- The original analysis thesis is still intact
- Price is in normal pullback/consolidation within the trade direction
- TP is still reachable from current price structure
- The position was opened recently and no structural invalidation has occurred yet
- Original void/pattern/level hasn't been violated
- Trade is at a loss but thesis isn't broken — ride it out

Rules:
- Respond with EXACTLY this JSON and nothing else:
  {"decision": "HOLD" or "CLOSE" or "SL+", "reason": "max 120 chars", "new_sl": <number or null>}
- "new_sl" is REQUIRED when decision is "SL+" — it must be a number (the new stop-loss price)
- "new_sl" must be null for HOLD and CLOSE decisions
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
        try:
            resp = await self.client.get(
                REFRESH_URL,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                new_token = (
                    data.get("token")
                    or data.get("access_token")
                    or data.get("data", {}).get("token")
                )
                if new_token:
                    self.token = new_token
                    print("[PositionAI] token refreshed")
                    return True
        except Exception as e:
            logger.warning(f"[PositionAI] Token refresh failed: {e}")
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

        # ── Build OHLCV blocks ─────────────────────────────────────────
        ohlcv_blocks = []
        for tf, candles in candles_by_tf.items():
            recent = candles[-80:]
            lines = [f"=== {symbol} | {tf} | {len(recent)} candles ===",
                     "timestamp, open, high, low, close, volume"]
            for c in recent:
                lines.append(f"{c[0]}, {c[1]}, {c[2]}, {c[3]}, {c[4]}, {c[5]}")
            ohlcv_blocks.append("\n".join(lines))

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
            f" Take Profit: {tp} ({pct_to_tp:+.3f}% away)\n"
            f" Stop Loss: {sl} (-{pct_to_sl:.3f}% away)\n"
            f" TP1 Level: {tp1 if tp1 else 'N/A'}\n"
            f" TP1 Hit: {'YES ✅' if tp1_hit else 'NO'}\n"
            f" {pnl_icon} Unrealized PnL: {sign}{pnl_pct}% ({sign}{pnl_usdt} USDT)\n"
            f" Leverage: {leverage}x\n"
            f" Margin Used: {margin_usdt} USDT\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{chr(10).join(ohlcv_blocks)}\n\n"
            f"Charts attached above.\n"
            f"Remember: this position was opened {elapsed_str}. "
            f"Judge whether the ORIGINAL THESIS is still valid — not just current price.\n"
            f"If TP1 has been HIT and position is in PROFIT → STRONGLY consider SL+ to lock gains.\n"
            f'Respond ONLY with JSON: {{"decision": "HOLD"|"CLOSE"|"SL+", "reason": "brief reason", "new_sl": <number or null>}}\n'
            f'For SL+: provide new_sl as a number (new stop-loss price). For HOLD/CLOSE: new_sl must be null.'
        )

        content = []
        if HAS_CHARTS:
            for tf, candles in candles_by_tf.items():
                img = _draw_chart(candles, symbol, tf)
                if img:
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img}"},
                    })
        content.append({"type": "text", "text": user_text})

        payload = {
            "model": QWEN_MODEL,
            "messages": [
                {"role": "system", "content": POSITION_SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            "stream": False,
            "thinking_mode": QWEN_THINKING,
            "max_tokens": 400,
        }

        lock = ai_lock()
        print(f"[PositionAI] waiting for lock ({symbol} {direction} pnl={sign}{pnl_pct}% elapsed={elapsed_str})")
        async with lock:
            print(f"[PositionAI] lock acquired → hold/close query for {symbol}")
            data = None
            for attempt in range(2):
                try:
                    resp = await self.client.post(
                        CHAT_URL,
                        headers={
                            "Authorization": f"Bearer {self.token}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                    if resp.status_code == 401:
                        if attempt == 0 and await self._refresh():
                            continue
                        return None
                    if resp.status_code == 429:
                        self.exhausted = True
                        print(f"[PositionAI] 🚫 Token slot={self.slot} rate-limited (429) — marked exhausted")
                        return None
                    if resp.status_code == 502:
                        try:
                            err = resp.json().get("error", {})
                            code = err.get("code", "")
                            detail = err.get("details", "") or err.get("message", "")
                        except Exception:
                            code, detail = "", ""
                        if code == "RateLimited" or "upper limit" in detail.lower() or "usage" in detail.lower():
                            self.exhausted = True
                            print(f"[PositionAI] 🚫 Token slot={self.slot} daily limit — marked exhausted")
                            return None
                        if code == "image_upload_failed":
                            # Jangan retry text-only — raise supaya pool bisa rotate ke token lain
                            print(f"[PositionAI] ⚠️ Image upload failed slot={self.slot} — raising for token rotation")
                            raise _ImageUploadFailed(f"image_upload_failed on slot {self.slot}")
                        logger.error(f"[PositionAI] HTTP 502 slot={self.slot}: {resp.text[:200]}")
                        return None
                    if resp.status_code != 200:
                        logger.error(f"[PositionAI] HTTP {resp.status_code}: {resp.text[:200]}")
                        return None
                    data = resp.json()
                    break
                except httpx.TimeoutException:
                    print(f"[PositionAI] timeout for {symbol} — will retry")
                    return None
                except Exception as e:
                    logger.error(f"[PositionAI] {e}")
                    return None

        if not data:
            return None

        try:
            full_text = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "") or ""
            )
        except Exception:
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
