"""
Qwen AI Client — drop-in replacement for deepseek_ai.py

Features:
 • Up to 5 bearer tokens (QWEN_TOKEN_1 .. QWEN_TOKEN_5) — round-robin + failover
 • Thinking mode ("Thinking") — deep step-by-step reasoning
 • Vision — sends candlestick chart PNG per timeframe alongside OHLCV text
 • Charts generated server-side with matplotlib (non-interactive Agg backend)
 • Auto token refresh via GET /v1/refresh on 401
 • Multi-target output: TP1, TP2, MAX

Railway env vars:
 QWEN_TOKEN_1 .. QWEN_TOKEN_5 ← bearer tokens from chat.qwen.ai (at least 1)
 QWEN_BASE_URL ← default: https://qwen-web-gateway.onrender.com
 QWEN_MODEL ← default: qwen3.6-plus
 QWEN_THINKING_MODE ← default: Thinking (Auto | Thinking | Fast)

Token expiry & refresh:
 Tokens are web-session cookies, NOT credit-based quotas — they don't "run out"
 on a schedule. They expire when the browser session expires (~24-48h idle).
 This client calls GET /v1/refresh automatically on every 401, so short-lived
 expiries are handled without manual intervention. For long-term reliability,
 keep 5 fresh tokens and rotate via QWEN_TOKEN_1..5.
"""

import asyncio
import base64
import io
import json
import logging
import mimetypes
import os
import time
import uuid
from typing import Dict, List, Optional

import httpx

from services.ai_lock import ai_lock

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config (Railway env vars)
# ---------------------------------------------------------------------------
BASE_URL = "https://chat.qwen.ai"

QWEN_MODEL = os.getenv("QWEN_MODEL", "").strip() or "qwen-latest-series-invite-beta-v24"
QWEN_THINKING = os.getenv("QWEN_THINKING_MODE", "").strip() or "Thinking"

# Kept for backward compatibility (position_ai.py may import these)
CHAT_URL = BASE_URL
REFRESH_URL = ""  # not used with reverse API

print(f"🌐 qwen_ai: direct reverse API → {BASE_URL}")
print(f"[qwen_ai] model={QWEN_MODEL!r} thinking={QWEN_THINKING!r}")


# ---------------------------------------------------------------------------
# Reverse API helpers — direct calls to chat.qwen.ai
# ---------------------------------------------------------------------------

def _qwen_headers(token: str, chat_id: str = None) -> dict:
    h = {
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "source": "web",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/147.0.0.0 Safari/537.36"
        ),
        "Origin": "https://chat.qwen.ai",
        "Version": "0.2.7",
        "bx-v": "2.5.36",
        "Authorization": f"Bearer {token}",
        "X-Request-Id": str(uuid.uuid4()),
    }
    if chat_id:
        h["Referer"] = f"https://chat.qwen.ai/c/{chat_id}"
    return h


async def _create_chat(token: str, client: "httpx.AsyncClient") -> Optional[str]:
    try:
        resp = await client.post(
            f"{BASE_URL}/api/v2/chats/new",
            headers=_qwen_headers(token),
            json={
                "title": "AI Analysis",
                "models": [QWEN_MODEL],
                "chat_mode": "normal",
                "chat_type": "t2t",
                "timestamp": int(time.time() * 1000),
                "project_id": "",
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["data"]["id"]
    except Exception as e:
        logger.warning(f"[qwen] _create_chat failed: {e}")
        return None


async def _delete_chat(token: str, chat_id: str, client: "httpx.AsyncClient"):
    try:
        await client.delete(
            f"{BASE_URL}/api/v2/chats/{chat_id}",
            headers=_qwen_headers(token),
            timeout=15,
        )
    except Exception:
        pass


async def _upload_image_bytes(
    token: str,
    image_bytes: bytes,
    filename: str,
    mime_type: str,
    client: "httpx.AsyncClient",
) -> Optional[dict]:
    """Upload image bytes to Qwen OSS. Returns dict with file_url, file_id, filename."""
    try:
        import oss2
    except ImportError:
        logger.warning("[qwen] oss2 not installed — image upload skipped (pip install oss2)")
        return None

    filetype = mime_type.split("/")[0]
    try:
        resp = await client.post(
            f"{BASE_URL}/api/v1/files/getstsToken",
            headers=_qwen_headers(token),
            json={"filename": filename, "filesize": len(image_bytes), "filetype": filetype},
            timeout=30,
        )
        resp.raise_for_status()
        d = resp.json()
    except Exception as e:
        logger.warning(f"[qwen] STS token request failed: {e}")
        return None

    try:
        auth = oss2.StsAuth(d["access_key_id"], d["access_key_secret"], d["security_token"])
        bucket = oss2.Bucket(auth, f"https://{d['region']}.aliyuncs.com", d["bucketname"])
        result = bucket.put_object(d["file_path"], image_bytes, headers={"Content-Type": mime_type})
        if result.status != 200:
            logger.warning(f"[qwen] OSS upload failed: {result.status}")
            return None
    except Exception as e:
        logger.warning(f"[qwen] OSS upload error: {e}")
        return None

    return {
        "file_url": d["file_url"],
        "file_id": d.get("file_id", ""),
        "filename": filename,
        "mime_type": mime_type,
    }


async def _send_stream(
    token: str,
    chat_id: str,
    prompt: str,
    client: "httpx.AsyncClient",
    files: list = None,
) -> str:
    """Send a message via reverse API and return the full streamed reply."""
    fid = str(uuid.uuid4())
    child_id = str(uuid.uuid4())
    ts = int(time.time())

    msg_files = []
    if files:
        for f in files:
            msg_files.append({
                "type": f["mime_type"].split("/")[0],
                "name": f["filename"],
                "url": f["file_url"],
                "file_id": f["file_id"],
                "size": 0,
                "file_type": f["mime_type"],
            })

    payload = {
        "stream": True,
        "version": "2.1",
        "incremental_output": True,
        "chat_id": chat_id,
        "chat_mode": "normal",
        "model": QWEN_MODEL,
        "parent_id": None,
        "messages": [{
            "fid": fid,
            "parentId": None,
            "childrenIds": [child_id],
            "role": "user",
            "content": prompt,
            "user_action": "chat",
            "files": msg_files,
            "timestamp": ts,
            "models": [QWEN_MODEL],
            "chat_type": "t2t",
            "feature_config": {
                "thinking_enabled": True,
                "output_schema": "phase",
                "research_mode": "normal",
                "auto_thinking": True,
                "thinking_mode": "enabled",
                "thinking_format": "summary",
                "auto_search": False,
            },
            "extra": {"meta": {"subChatType": "t2t"}},
            "sub_chat_type": "t2t",
            "parent_id": None,
        }],
        "timestamp": ts + 1,
    }

    headers = {**_qwen_headers(token, chat_id), "x-accel-buffering": "no"}
    full_reply = ""
    full_thoughts = []

    try:
        async with client.stream(
            "POST",
            f"{BASE_URL}/api/v2/chat/completions?chat_id={chat_id}",
            headers=headers,
            json=payload,
            timeout=180,
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                logger.warning(f"[qwen] _send_stream HTTP {resp.status_code}: {body.decode()[:300]}")
                return ""

            async for line in resp.aiter_lines():
                if not line:
                    continue
                data_str = line[6:] if line.startswith("data: ") else line
                if data_str.strip() == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                except Exception:
                    continue

                if data.get("success") is False:
                    err = data.get("data", {})
                    logger.warning(f"[qwen] API error: {err.get('code')} — {err.get('details')}")
                    break

                choices = data.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                content_chunk = delta.get("content", "")
                phase = delta.get("phase", "")
                extra = delta.get("extra", {})
                status = delta.get("status", "")
                finish_reason = choices[0].get("finish_reason", "")

                if phase == "thinking_summary":
                    # Internal reasoning phase — store as fallback only.
                    # DO NOT break here; the actual JSON answer arrives as
                    # regular content chunks AFTER thinking finishes.
                    thoughts = extra.get("summary_thought", {}).get("content", [])
                    if thoughts:
                        full_thoughts = thoughts
                else:
                    # Regular answer chunks (JSON response lives here)
                    if content_chunk:
                        full_reply += content_chunk

                if finish_reason == "stop":
                    break
    except Exception as e:
        logger.warning(f"[qwen] _send_stream error: {e}")

    return full_reply

# ---------------------------------------------------------------------------
# Training images — loaded once at startup from services/ directory
# ---------------------------------------------------------------------------
_SERVICES_DIR = os.path.dirname(os.path.abspath(__file__))
_TRAINING_IMAGES: List[str] = []  # list of base64-encoded JPG strings

def _load_training_images() -> List[str]:
    """
    Load training1.jpg .. training5.jpg from the same directory as this file.
    Returns list of base64 strings. Missing files are silently skipped.
    """
    images = []
    for i in range(1, 6):
        path = os.path.join(_SERVICES_DIR, f"training{i}.jpg")
        if not os.path.exists(path):
            continue
        try:
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            images.append(b64)
            print(f"📚 qwen_ai: training{i}.jpg loaded ({len(b64)//1024}KB)")
        except Exception as e:
            logger.warning(f"qwen_ai: failed to load training{i}.jpg — {e}")
    if images:
        print(f"📚 qwen_ai: {len(images)} training image(s) ready — will be sent with every analysis")
    else:
        print("⚠️  qwen_ai: no training images found in services/ (training1.jpg .. training5.jpg)")
    return images

_TRAINING_IMAGES = _load_training_images()

# ---------------------------------------------------------------------------
# Chart generation (matplotlib — non-interactive Agg backend)
# ---------------------------------------------------------------------------
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_CHARTS = True
    logger.info("matplotlib loaded — candlestick charts enabled")
    print("📊 qwen_ai: matplotlib OK — charts will be sent with each analysis")
except ImportError:
    HAS_CHARTS = False
    logger.warning("matplotlib not installed — falling back to text-only mode")
    print("⚠️ qwen_ai: matplotlib not found — text-only mode (pip install matplotlib)")


def _draw_chart(candles: list, symbol: str, tf: str) -> Optional[str]:
    """Render a dark-theme OHLCV candlestick + volume chart."""
    if not HAS_CHARTS or not candles:
        return None

    data = candles[-150:]
    n = len(data)

    try:
        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(13, 7),
            gridspec_kw={"height_ratios": [3, 1]},
            facecolor="#0d1117",
        )
        ax1.set_facecolor("#0d1117")
        ax2.set_facecolor("#0d1117")

        for i, c in enumerate(data):
            try:
                o, h, l, close = float(c[1]), float(c[2]), float(c[3]), float(c[4])
                vol = float(c[5]) if len(c) > 5 else 0.0
            except (IndexError, ValueError, TypeError):
                continue

            bull = close >= o
            color = "#26a69a" if bull else "#ef5350"
            ax1.plot([i, i], [l, h], color=color, linewidth=0.6, zorder=1)
            body_y = min(o, close)
            body_h = max(abs(close - o), (h - l) * 0.004)
            ax1.add_patch(
                plt.Rectangle(
                    (i - 0.38, body_y), 0.76, body_h,
                    color=color, linewidth=0, zorder=2,
                )
            )
            ax2.bar(i, vol, color=color, alpha=0.72, width=0.8)

        ax1.set_title(
            f"{symbol} · {tf} · {n} candles",
            color="#e0e0e0", fontsize=10, pad=6,
        )
        ax1.set_xlim(-1, n)
        ax2.set_xlim(-1, n)
        ax1.set_xticks([])
        ax2.set_xlabel("candle index", color="#444", fontsize=7)

        for ax in (ax1, ax2):
            ax.tick_params(colors="#666", labelsize=6.5)
            for spine in ax.spines.values():
                spine.set_edgecolor("#2a2a2a")
            ax.yaxis.set_tick_params(labelcolor="#aaa")

        plt.tight_layout(pad=0.4)

        buf = io.BytesIO()
        plt.savefig(
            buf, format="png", dpi=75,
            bbox_inches="tight", facecolor="#0d1117",
        )
        buf.seek(0)
        img_b64 = base64.b64encode(buf.read()).decode()
        plt.close(fig)
        return img_b64

    except Exception as e:
        logger.warning(f"Chart render failed {symbol}/{tf}: {e}")
        try:
            plt.close("all")
        except Exception:
            pass
        return None


def _generate_all_charts(candles_by_tf: dict, symbol: str) -> Dict[str, str]:
    result = {}
    for tf, candles in candles_by_tf.items():
        img = _draw_chart(candles, symbol, tf)
        if img:
            result[tf] = img
    return result


# ---------------------------------------------------------------------------
# System prompt — strategy rules (CORE UNCHANGED) + TP1/TP2/MAX addition
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are an AI trained to mimic a specific trading strategy based on example data.

Your job:
- Learn from the examples
- Apply the SAME behavior to new data

Focus on:
- Wick behavior (rejection / inefficiency)
- Void detection and positioning
- Candle relationships
- Multi-timeframe context (HTF vs LTF)
- Volume delta / CVD confirmation
- Session context

---
BACKEND CONTEXT RULE (CRITICAL):
The backend will provide pre-computed market structure, trend, swing points, volume delta, and session.
- DO NOT determine trend direction yourself from raw candles — use backend trend_4h / trend_1h
- DO NOT classify HH/HL/LH/LL yourself — use backend swing_points
- Your job is ONLY: find void, find wick, find entry
- If backend provides allow_reversal=false → DO NOT enter counter-trend, even if you see a pattern
- If backend trend is not provided → you may infer, but mark confidence lower

---
STRICT TREND RULE:
- UP (from backend) → ONLY LONG
- DOWN (from backend) → ONLY SHORT
- Do NOT counter-trade unless allow_reversal=true AND all reversal conditions are met

---
VOLUME DELTA / CVD ANTI-FAKE RULE:
- If breakout void + delta/CVD bullish → VALID LONG
- If breakout void + delta/CVD bearish → FAKE / SKIP
- If wick rejection + buyer_pressure weak → SKIP
- Low volume candles near void → treat with caution
- This is your PRIMARY anti-fake filter

---
SESSION AWARENESS RULE:
- ASIA session: lower liquidity, more fake moves — require stronger void
- LONDON / NY_OPEN: high validity — voids in these sessions most reliable
- NY_AFTERNOON / ASIA_PRE: declining volume — be more selective
- Session info provided by backend

---
WICK + VOID DIRECTION RULE (CRITICAL):

- UP trend:
  → use UPPER WICK voids (see some candle before)
  → ignore lower wick voids

- DOWN trend:
  → use lower WICK voids (see some candle before)
  → ignore upper wick voids

IMPORTANT:
- The void must be in the direction of a RETRACEMENT, not continuation

Logic:
- LONG = buy lower → void must be BELOW current price
- SHORT = sell higher → void must be ABOVE current price

- NEVER choose a void that would require chasing price

---
ENTRY DISTANCE RULE:
- Entry MUST be placed at a clear void
- Entry must NOT be near current price without structure
- If price is already near the level → NO TRADE
- Entry should feel like a LIMIT order (far from price), not a market entry

---
NO TRADE RULE:
- No clear void → NO TRADE
- Bad structure → NO TRADE
- Entry too close to price → NO TRADE
- If very low volume → NO TRADE

---
REVERSAL RULE (ADVANCED):
Reversal trades are allowed ONLY if ALL conditions are met:

1. There is a clear void (4H / 2H — if found on a higher timeframe, check further back
   on a lower timeframe; if a pattern similar to the training data exists, verify the
   previous high/low from the higher timeframe)
2. The level comes from past price action (look-back structure)
3. The level has NOT been revisited

If ALL valid → Counter-trend entry is allowed
If NOT → Stay with trend or NO TRADE

---
PRIORITY RULE:
1. Primary → Trend-following setups
2. Secondary → Reversal (ONLY with strong HTF confirmation)

---
ANTI-FAKE RULE:
- Do NOT assume reversal randomly
- Do NOT force trades
- If unsure → NO TRADE

---
MULTI-TARGET RULE (TP1 / TP2 / MAX):
- Every valid trade MUST have 3 profit targets: TP1, TP2, MAX
- TP1 = nearest realistic target (1:1 to 1:2 R/R). This is the "safe" take.
- TP2 = intermediate target (1:2 to 1:3 R/R). This is the "aggressive" take.
- MAX = maximum realistic extension (1:3+ R/R or next major HTF level). This is the "moon" take.
- Risk/Reward is calculated from ENTRY to each TP, with SL as risk.
- TP1 MUST be closer to entry than TP2. TP2 MUST be closer than MAX.
- For LONG: TP1 < TP2 < MAX (all above entry)
- For SHORT: TP1 > TP2 > MAX (all below entry)

---
TRAINING DATA:

[
  {
    "input": "the trend is going down; found this on the 4h timeframe: o:0.003942 h:0.003979 l:0.003791 c:0.003843 v:246.84M; +1 o:0.003844 h:0.003887 l:0.003831 c:0.003835 v:103.39M; -1 o:0.003858 h:0.003942 l:0.003845 c:0.003941 v:98.58M — enter at the last wick body candle from that void",
    "output": "limit short at 0.003942 (trend down, level not yet touched)"
  },
  {
    "input": "trend is up; looking for short entry; -1 o:0.0004684 h:0.0004692 l:0.0004635 c:0.0004637; main o:0.0004636 h:0.0004646 l:0.0004539 c:0.0004582; +1 o:0.0004581 h:0.0004585 l:0.0004556 c:0.0004570; +2 o:0.0004570 h:0.0004570 l:0.0004526 c:0.0004541 — main candle long wick, next candle does not close it → void",
    "output": "entry short at 0.0004582 (body close of last wick candle)"
  },
  {
    "input": "trend up; looking for long; o:13.33160 h:13.73500 l:13.10230 c:13.21796; +1 o:13.21795 h:13.26964 l:13.04792 c:13.22730; +2 o:13.22775 h:13.87839 l:13.20719 c:13.81678; -1 o:13.23907 h:13.33333 l:13.06984 c:13.33331; -2 o:13.04731 h:13.24540 l:12.98318 c:13.23923 — wick then gap then close: void in the middle",
    "output": "entry long at 13.33160 (candle body open)"
  },
  {
    "input": "trend up; 3m; o:2.42663 h:2.97600 l:2.35226 c:2.48033; +1 o:2.48030 h:2.52137 l:2.25767 c:2.40491; +2 o:2.40507 h:2.49556 l:2.33333 c:2.43605; -1 o:2.05480 h:2.56645 l:2.05450 c:2.42613; -2 o:2.01596 h:2.05789 l:2.01000 c:2.05443",
    "output": "entry long at 2.42613 (void confirmed)"
  },
  {
    "input": "same void on 15m: o:2.01596 h:2.97600 l:2.01000 c:2.48033; +1 o:2.48030 h:2.52137 l:2.25767 c:2.45024; +2 o:2.45016 h:3.17200 l:2.44670 c:2.77272; -1 o:1.97052 h:2.03159 l:1.95600 c:2.01583",
    "output": "entry long at 2.48033 (queue on 15m timeframe)"
  },
  {
    "input": "trend down on 15m; o:16.69993 h:16.91653 l:13.86700 c:15.71328; -3 empty -4 wick -5 last wick; -5 o:17.52713 h:17.63100 l:16.64201 c:17.21921",
    "output": "entry short at 17.21921 (body close of last wick, void behind)"
  }
]"""


# ---------------------------------------------------------------------------
# Single-token Qwen client
# ---------------------------------------------------------------------------

class QwenAIClient:
    """One bearer token = one independent Qwen API client."""

    def __init__(self, token: str, slot: int):
        self.token = token
        self.slot = slot
        self._tag = f"[QW-{slot}]"
        self.exhausted = False  # True kalau kena rate limit harian
        self.client = httpx.AsyncClient(timeout=240)
        # Per-instance lock — memastikan 1 token tidak dipakai 2 request bersamaan,
        # tapi token BERBEDA bisa jalan paralel tanpa saling blokir.
        self._lock: asyncio.Lock | None = None

    def _get_lock(self) -> asyncio.Lock:
        """Lazy-init per-client lock (harus dibuat di dalam running event loop)."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def _refresh(self) -> bool:
        """Token refresh not applicable with reverse API."""
        return False

    async def analyze(
        self,
        symbol: str,
        candles_by_tf: dict,
        current_price: float = None,
        backend_context: dict = None,
        leverage: int = 10,
    ) -> dict:
        tag = self._tag
        logger.info(f"{tag} Starting analysis for {symbol}")

        # ── 1. Generate candlestick charts ────────
        loop = asyncio.get_event_loop()
        charts: Dict[str, str] = {}
        try:
            charts = await loop.run_in_executor(
                None, _generate_all_charts, candles_by_tf, symbol
            )
            if charts:
                print(f"{tag} 📊 {symbol} charts ready: {list(charts.keys())}")
            else:
                print(f"{tag} ⚠️ {symbol} charts skipped")
        except Exception as e:
            logger.warning(f"{tag} Chart generation error for {symbol}: {e}")

        # ── 2. Build OHLCV text blocks ────────────────────────────────
        tf_blocks = []
        last_candle_price = None

        for tf in ["5m", "15m", "30m", "1h", "4h"]:
            candles = candles_by_tf.get(tf, [])
            if not candles:
                continue
            lines = [
                f"=== {symbol} | {tf} | last {min(len(candles), 150)} candles ===",
                "timestamp, open, high, low, close, volume",
            ]
            for c in candles[-150:]:
                lines.append(f"{c[0]}, {c[1]}, {c[2]}, {c[3]}, {c[4]}, {c[5]}")
            tf_blocks.append("\n".join(lines))
            last_candle_price = float(candles[-1][4])

        live_price = current_price if (current_price and current_price > 0) else last_candle_price
        ohlcv_text = "\n\n".join(tf_blocks) if tf_blocks else "No candle data available."

        # ── Leverage-aware SL/TP minimum distances ─────────────────────
        # min_sl_pct: minimum price % distance from entry for SL.
        # Rule: target ~15% ROE equivalent, floor at 0.20% to always cover fees.
        # Examples: 50x → 0.30% | 20x → 0.75% | 10x → 1.50%
        min_sl_pct    = max(round(15 / leverage, 2), 0.20)
        min_tp2_pct   = round(min_sl_pct * 2, 2)
        min_tpmax_pct = round(min_sl_pct * 3, 2)

        # ── Build backend context block ───────────────────────────────
        bc = backend_context or {}
        backend_block = ""
        if bc:
            ms = bc.get("market_structure", {})
            swings = bc.get("swing_points", {})
            vd = bc.get("volume_delta", {})
            session = bc.get("session", "UNKNOWN")
            allow_reversal = bc.get("allow_reversal", True)
            atr = bc.get("atr", {})

            ms_lines = "\n".join(f"  {tf}: {s}" for tf, s in ms.items()) if ms else "  N/A"
            swing_lines = []
            for tf, sp in swings.items():
                swing_lines.append(
                    f"  {tf}: HH={sp.get('last_hh')} HL={sp.get('last_hl')} "
                    f"LH={sp.get('last_lh')} LL={sp.get('last_ll')}"
                )
            swing_text = "\n".join(swing_lines) if swing_lines else "  N/A"
            vd_lines = "\n".join(
                f"  {tf}: cvd={v.get('cvd_last_20')} delta5={v.get('delta_last_5')} pressure={v.get('buyer_pressure')}"
                for tf, v in vd.items()
            ) if vd else "  N/A"
            atr_lines = "\n".join(f"  {tf}: {v}" for tf, v in atr.items()) if atr else "  N/A"

            backend_block = f"""
━━━ BACKEND PRE-COMPUTED CONTEXT (USE THIS — DO NOT OVERRIDE) ━━━
 Session: {session}
 Allow Reversal: {"YES" if allow_reversal else "NO — trend-following ONLY"}

 Market Structure (per TF):
{ms_lines}

 Swing Points (per TF):
{swing_text}

 Volume Delta / CVD (per TF):
{vd_lines}

 ATR (per TF):
{atr_lines}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USE backend Market Structure for trend direction.
USE Volume Delta pressure to validate or reject void setups.
If buyer_pressure = divergence and direction = LONG → treat as FAKE/NO TRADE.
If session = ASIA and volume is low → require stronger void confirmation.
"""

        # Build training image description block
        n_training = len(_TRAINING_IMAGES)
        n_charts = len(charts)
        if n_training > 0:
            training_img_block = f"""---
TRAINING REFERENCE IMAGES ({n_training} image{'s' if n_training > 1 else ''}):
The first {n_training} image{'s' if n_training > 1 else ''} attached (before the candlestick charts) are REAL TRADE EXAMPLES from the target strategy.
Each image shows an annotated chart of a valid setup: void location, wick structure, entry zone, and TP/SL placement.
Study these images carefully to understand the VISUAL PATTERN you must replicate.
Use them as ground truth for what a valid void/wick setup looks like.
"""
        else:
            training_img_block = ""

        if n_charts > 0:
            chart_img_block = f"""---
LIVE CANDLESTICK CHARTS ({n_charts} image{'s' if n_charts > 1 else ''} — timeframes: {', '.join(charts.keys())}):
The remaining images are server-generated candlestick charts of the current {symbol} data.
Use BOTH the chart images AND the OHLCV text to identify void.
Cross-reference: what you see visually in the charts should match the OHLCV numbers.
"""
        else:
            chart_img_block = ""

        prompt_text = f"""Analyze {symbol}

{ohlcv_text}

{training_img_block}
{chart_img_block}
{backend_block}
⚠️ CURRENT REALTIME PRICE: {live_price}
(This is the live ticker price — use it as the reference for entry placement)

---
VOID POSITION RULE (CRITICAL):
- LONG → void MUST be BELOW current price ({live_price})
- SHORT → void MUST be ABOVE current price ({live_price})
- If void is on the wrong side → IGNORE IT
- If no valid void on correct side → NO TRADE

ENTRY DIRECTION RULE (CRITICAL — violations cause instant loss):
- LONG → entry MUST be BELOW {live_price}
- SHORT → entry MUST be ABOVE {live_price}
- NEVER: ❌ LONG above price | ❌ SHORT below price

---
Respond in this EXACT JSON format ONLY — no preamble, no markdown:

{{
  "trend": "UP" or "DOWN" or "SIDEWAYS",
  "pattern": "brief description of void/wick pattern detected",
  "decision": "LONG" or "SHORT" or "NO TRADE",
  "entry": <number>,
  "tp1": <number>,
  "tp2": <number>,
  "tp_max": <number>,
  "sl": <number>,
  "invalidation": <number>,
  "reason": "short explanation referencing the void/wick imbalance",
  "confidence": <0-100>
}}

TP RULES:
- tp1 = nearest target (1:1~1:2 R/R). MUST be realistic.
- tp2 = intermediate target (1:2~1:3 R/R). MUST be further than tp1.
- tp_max = max extension target (1:3+ R/R or next HTF level). MUST be furthest.
- For LONG: entry < tp1 < tp2 < tp_max
- For SHORT: entry > tp1 > tp2 > tp_max

---
LEVERAGE CONTEXT — THIS TRADE USES {leverage}x LEVERAGE:
- At {leverage}x: a 1% price move = {leverage}% ROE
- Minimum viable SL distance from entry: {min_sl_pct:.2f}% (= ~{leverage * min_sl_pct:.0f}% ROE)
- Anything tighter than {min_sl_pct:.2f}% is ENTRY NOISE at {leverage}x — not a real invalidation

SL RULES — MANDATORY:
- SL MUST be placed at a structural level: below nearest swing low (LONG) or above swing high (SHORT)
- SL distance from entry MUST be ≥ {min_sl_pct:.2f}% — no exceptions
- SL must NEVER equal entry price — fees will eat the trade before price moves
- If no structural SL level exists at ≥ {min_sl_pct:.2f}% from entry → return NO TRADE
- Fee context: round-trip taker fees ≈ 0.08% of notional — SL distance must cover this

TP CALIBRATION ({leverage}x leverage):
- TP1 must be ≥ {min_sl_pct:.2f}% from entry (1:1 R:R minimum — closer than this loses to fees)
- TP2 must be ≥ {min_tp2_pct:.2f}% from entry
- tp_max must be ≥ {min_tpmax_pct:.2f}% from entry or next major HTF level

If there is NO clear void/imbalance setup → return "NO TRADE". Do NOT force a trade."""

        # ── 3. Upload images to Qwen OSS ────────────────────────────
        uploaded_files = []
        if _TRAINING_IMAGES:
            print(f"{tag} 📤 Uploading {len(_TRAINING_IMAGES)} training image(s) for {symbol}...")
            for i, img_b64 in enumerate(_TRAINING_IMAGES):
                uf = await _upload_image_bytes(
                    self.token, base64.b64decode(img_b64),
                    f"training{i + 1}.jpg", "image/jpeg", self.client,
                )
                if uf:
                    uploaded_files.append(uf)
        for tf, img_b64 in charts.items():
            uf = await _upload_image_bytes(
                self.token, base64.b64decode(img_b64),
                f"chart_{symbol}_{tf}.png", "image/png", self.client,
            )
            if uf:
                uploaded_files.append(uf)
        if uploaded_files:
            print(f"{tag} 📷 {len(uploaded_files)} image(s) uploaded for {symbol}")

        # Prepend system prompt (reverse API has no dedicated system field)
        full_prompt = SYSTEM_PROMPT + "\n\n---\n\n" + prompt_text

        # ── 4. Create chat, stream response, cleanup ─────────────────
        # Gunakan per-client lock supaya token berbeda bisa jalan paralel.
        full_text = ""
        chat_id = None  # akan diisi saat create_chat berhasil; dipakai position_ai untuk monitoring
        async with self._get_lock():
            for attempt in range(2):
                try:
                    print(f"{tag} 🔄 Qwen reverse API [{QWEN_MODEL}] for {symbol} (attempt {attempt + 1})")
                    chat_id = await _create_chat(self.token, self.client)
                    if not chat_id:
                        if attempt == 0:
                            continue
                        return self._no_trade("Failed to create chat session")

                    raw_reply = await _send_stream(
                        self.token, chat_id, full_prompt, self.client, uploaded_files or None
                    )
                    # Jangan delete chat — room ini akan dilanjutkan oleh position_ai
                    # untuk monitoring. Chat akan dihapus oleh bot_engine saat posisi ditutup.

                    if raw_reply:
                        import re
                        full_text = re.sub(r"<think>.*?</think>", "", raw_reply, flags=re.DOTALL).strip()
                        break

                    if attempt == 0:
                        # Gagal dapat reply — hapus chat ini dan coba buat baru
                        await _delete_chat(self.token, chat_id, self.client)
                        chat_id = None
                        continue
                    return self._no_trade("Empty stream response after retries")

                except Exception as e:
                    logger.error(f"{tag} Request exception for {symbol}: {e}", exc_info=True)
                    return self._no_trade(f"Request error: {e}")

        logger.info(f"{tag} Raw response for {symbol} ({len(full_text)} chars):\n{full_text[:600]}")
        print(f"{tag} RAW [{symbol}]: {full_text[:400]}")

        if not full_text.strip():
            return self._no_trade("Empty AI response")

        # ── 6. Parse JSON ───────────────────────────────
        start = full_text.find("{")
        end = full_text.rfind("}") + 1

        if start < 0 or end <= start:
            logger.error(f"{tag} No JSON found for {symbol}. Response: {full_text[:500]}")
            return self._no_trade("No JSON in AI response")

        json_str = full_text[start:end]
        try:
            result = json.loads(json_str)
        except json.JSONDecodeError as je:
            logger.error(f"{tag} JSON decode error for {symbol}: {je}")
            return self._no_trade(f"JSON parse error: {je}")

        decision = result.get("decision", "NO TRADE").upper().strip()
        if decision not in ("LONG", "SHORT", "NO TRADE"):
            logger.warning(f"{tag} Unexpected decision '{decision}' for {symbol} — forcing NO TRADE")
            decision = "NO TRADE"

        parsed = {
            "trend": result.get("trend", "SIDEWAYS"),
            "pattern": result.get("pattern", ""),
            "decision": decision,
            "entry": result.get("entry"),
            "tp1": result.get("tp1"),
            "tp2": result.get("tp2"),
            "tp_max": result.get("tp_max"),
            "tp": result.get("tp1"),
            "sl": result.get("sl"),
            "invalidation": result.get("invalidation"),
            "reason": result.get("reason", ""),
            "confidence": int(result.get("confidence", 0)),
            # Disimpan agar position_ai bisa melanjutkan di room chat yang sama
            "original_prompt": full_prompt,
            "original_ai_response": full_text,
            # Chat room dari analisa ini — position_ai akan pakai room yang sama
            # sehingga AI sudah punya konteks penuh dari analisa awal.
            # bot_engine wajib memanggil _delete_chat() saat posisi ditutup.
            "qwen_chat_id": chat_id,
            "qwen_token": self.token,
        }

        print(
            f"{tag} ✅ {symbol} → {decision} "
            f"entry={parsed['entry']} tp1={parsed['tp1']} tp2={parsed['tp2']} max={parsed['tp_max']} conf={parsed['confidence']}%"
        )
        return parsed

    def _no_trade(self, reason: str) -> dict:
        logger.warning(f"{self._tag} NO TRADE — {reason}")
        return {
            "trend": "SIDEWAYS",
            "pattern": "none",
            "decision": "NO TRADE",
            "entry": None,
            "tp1": None,
            "tp2": None,
            "tp_max": None,
            "tp": None,
            "sl": None,
            "invalidation": None,
            "reason": reason,
            "confidence": 0,
        }

    async def close(self):
        await self.client.aclose()


# ---------------------------------------------------------------------------
# Parallel wrapper
# ---------------------------------------------------------------------------

class ParallelQwenAI:
    def __init__(self):
        self.clients: List[QwenAIClient] = []
        self._rr_idx = 0

        for slot in range(1, 6):
            token = os.getenv(f"QWEN_TOKEN_{slot}", "").strip()
            if token:
                self.clients.append(QwenAIClient(token=token, slot=slot))
                logger.info(f"[ParallelQwen] Token slot {slot} registered")
                print(f"[ParallelQwen] ✅ Token {slot} loaded")

        if not self.clients:
            logger.error("[ParallelQwen] No tokens configured! Set QWEN_TOKEN_1 at minimum.")
            print("[ParallelQwen] ❌ No Qwen tokens found in environment!")
        else:
            print(
                f"[ParallelQwen] {len(self.clients)} token(s) | "
                f"model={QWEN_MODEL} | thinking={QWEN_THINKING} | "
                f"charts={'ON' if HAS_CHARTS else 'OFF (install matplotlib)'}"
            )

    def reload_tokens(self):
        """
        Hot-reload token list dari token_manager tanpa restart server.
        Dipanggil oleh admin_routes setelah update via API.
        """
        from services.token_manager import token_manager  # local import — hindari circular

        # Tutup client lama
        for client in self.clients:
            # httpx.AsyncClient.aclose() adalah coroutine — jadwalkan kalau ada loop
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(client.close())
            except Exception:
                pass

        # Buat client baru dari token terbaru
        self.clients = []
        self._rr_idx = 0
        for slot, token in enumerate(token_manager.get_tokens(), 1):
            if token:
                self.clients.append(QwenAIClient(token=token, slot=slot))
                print(f"[ParallelQwen] 🔄 Token slot {slot} reloaded")

        print(f"[ParallelQwen] reload_tokens: {len(self.clients)} active token(s)")

    def _available_clients(self) -> list:
        """Return clients yang belum exhausted. Kalau semua exhausted, return semua (reset)."""
        available = [c for c in self.clients if not c.exhausted]
        if not available:
            # Semua exhausted — reset dan coba lagi (mungkin sudah lewat tengah malam)
            print("[ParallelQwen] All tokens exhausted — resetting exhausted flags (retry)")
            for c in self.clients:
                c.exhausted = False
            available = self.clients
        return available

    # ── Error reasons yang memicu rotate token ──────────────────────────────
    # Token hanya diganti kalau terjadi error ini. Error lain (timeout, JSON
    # parse, dll) TIDAK merotate — tetap pakai token yang sama.
    _ROTATE_REASONS = ("RateLimited", "HTTP 502")

    def _should_rotate(self, reason: str) -> bool:
        return any(r in reason for r in self._ROTATE_REASONS)

    def _current_client(self) -> "QwenAIClient | None":
        """Return token aktif saat ini (non-exhausted). Rotate kalau exhausted."""
        available = self._available_clients()
        if not available:
            return None
        return available[self._rr_idx % len(available)]

    def _rotate(self, reason: str = ""):
        """Advance ke token berikutnya dan log alasannya."""
        self._rr_idx += 1
        client = self._current_client()
        slot = client.slot if client else "?"
        print(f"[QwenAI] 🔄 Token rotated → slot {slot} | reason: {reason}")

    async def analyze_parallel(self, items: list, concurrency: int = 3) -> list:
        """
        Analisis beberapa simbol secara PARALEL — masing-masing pakai token berbeda.

        items: list of tuples (symbol, candles_by_tf, current_price, backend_context, leverage)
               — current_price, backend_context, dan leverage boleh None/omitted.
        concurrency: jumlah token paralel (default 3, max = jumlah token tersedia).

        Return: list hasil dalam urutan yang sama dengan items.

        Cara kerja:
          - Item ke-0 → token ke-0, item ke-1 → token ke-1, dst.
          - Kalau items > concurrency, item sisanya diproses di batch berikutnya
            (caller bertanggung jawab membatasi jumlah items).
          - Kalau suatu token dapat 502/RateLimited, rotate dan retry sekali.
        """
        if not self.clients:
            return [self._no_trade("No tokens configured")] * len(items)

        available = self._available_clients()
        n = min(len(items), concurrency, len(available))

        if n == 0:
            return [self._no_trade("No tokens available")] * len(items)

        print(
            f"[QwenAI] analyze_parallel: {len(items)} symbol(s) → "
            f"{n} parallel slot(s) | tokens: {[available[i % len(available)].slot for i in range(n)]}"
        )

        # Dispatch setiap item ke token berbeda
        tasks = []
        for i, item in enumerate(items[:n]):
            sym   = item[0]
            tfs   = item[1]
            price = item[2] if len(item) > 2 else None
            bctx  = item[3] if len(item) > 3 else None
            lev   = item[4] if len(item) > 4 else 10
            client = available[i % len(available)]
            tasks.append(self._analyze_with_client(client, sym, tfs, price, bctx, lev))

        gathered = await asyncio.gather(*tasks, return_exceptions=True)

        final = []
        for r in gathered:
            if isinstance(r, Exception):
                final.append(self._no_trade(f"Task exception: {r}"))
            elif isinstance(r, dict):
                final.append(r)
            else:
                final.append(self._no_trade(str(r)))

        # Items di luar concurrency limit (harusnya tidak ada kalau caller membatasi batch)
        for item in items[n:]:
            final.append(self._no_trade("Skipped — beyond concurrency limit"))

        return final

    async def _analyze_with_client(
        self,
        client: "QwenAIClient",
        symbol: str,
        candles_by_tf: dict,
        current_price: float = None,
        backend_context: dict = None,
        leverage: int = 10,
    ) -> dict:
        """Analisis satu simbol dengan client tertentu; rotate+retry kalau 502/RateLimited."""
        result = await client.analyze(symbol, candles_by_tf, current_price, backend_context, leverage)

        if self._should_rotate(result.get("reason", "")):
            self._rotate(result["reason"])
            retry = self._current_client()
            if retry and retry is not client:
                print(f"[QwenAI] Retry {symbol} → slot {retry.slot}")
                result = await retry.analyze(symbol, candles_by_tf, current_price, backend_context, leverage)

        return result

    async def analyze_batch(self, items: list) -> list:
        """
        Proses semua item menggunakan 1 token aktif secara paralel.
        Rotate token hanya kalau ada item yang error 502 / RateLimited.
        Item yang error di-retry dengan token baru — bukan paralel multi-token.
        Item format: (symbol, candles_by_tf, price) atau (symbol, candles_by_tf, price, backend_context)
        """
        if not self.clients:
            return [self._no_trade("No tokens configured")] * len(items)

        client = self._current_client()
        if not client:
            return [self._no_trade("No tokens available")] * len(items)

        print(f"[QwenAI] analyze_batch: {len(items)} item(s) via token slot {client.slot} (sequential)")

        # Proses satu per satu — bukan paralel
        final = []
        for item in items:
            sym   = item[0]
            tfs   = item[1]
            price = item[2] if len(item) > 2 else None
            bctx  = item[3] if len(item) > 3 else None

            # Ambil token aktif saat ini (bisa berubah kalau terjadi rotate)
            cur = self._current_client()
            if not cur:
                final.append(self._no_trade("No tokens available"))
                continue

            try:
                r = await cur.analyze(sym, tfs, price, bctx)
            except Exception as e:
                r = self._no_trade(f"Task exception: {e}")

            # Rotate hanya kalau error 502 / RateLimited, lalu retry sekali
            reason = r.get("reason", "") if isinstance(r, dict) else ""
            if self._should_rotate(reason):
                self._rotate(reason)
                retry = self._current_client()
                if retry and retry is not cur:
                    print(f"[QwenAI] Retry {sym} → slot {retry.slot}")
                    try:
                        r = await retry.analyze(sym, tfs, price, bctx)
                    except Exception as e:
                        r = self._no_trade(f"Retry failed: {e}")

            final.append(r if isinstance(r, dict) else self._no_trade(str(r)))

        return final

    async def analyze(
        self,
        symbol: str,
        candles_by_tf: dict,
        current_price: float = None,
        backend_context: dict = None,
        leverage: int = 10,
    ) -> dict:
        """
        Analisis satu simbol dengan token aktif saat ini.
        Rotate ke token berikutnya HANYA kalau dapat 502 atau RateLimited.
        """
        if not self.clients:
            return self._no_trade("No tokens configured")

        client = self._current_client()
        if not client:
            return self._no_trade("No tokens available")

        result = await client.analyze(symbol, candles_by_tf, current_price, backend_context, leverage)

        if self._should_rotate(result.get("reason", "")):
            self._rotate(result["reason"])
            retry_client = self._current_client()
            if retry_client and retry_client is not client:
                print(f"[QwenAI] Retry {symbol} → slot {retry_client.slot}")
                result = await retry_client.analyze(symbol, candles_by_tf, current_price, backend_context, leverage)

        return result

    def _no_trade(self, reason: str) -> dict:
        return {
            "trend": "SIDEWAYS",
            "pattern": "none",
            "decision": "NO TRADE",
            "entry": None,
            "tp1": None,
            "tp2": None,
            "tp_max": None,
            "tp": None,
            "sl": None,
            "invalidation": None,
            "reason": reason,
            "confidence": 0,
        }

    async def close(self):
        for client in self.clients:
            await client.close()


qwen_ai = ParallelQwenAI()
