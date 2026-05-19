"""
Qwen AI Client — drop-in replacement for deepseek_ai.py

Features:
 • Up to 5 bearer tokens (QWEN_TOKEN_1 .. QWEN_TOKEN_5) — round-robin + failover
 • Thinking mode ("Thinking") — deep step-by-step reasoning
 • Vision — sends candlestick chart PNG per timeframe alongside OHLCV text
 • Charts generated server-side with matplotlib (non-interactive Agg backend)
 • Auto token refresh via GET /v1/refresh on 401
 • Multi-target output: TP1, TP2, MAX
 • PARALLEL execution: multiple tokens, per-client lock prevents same-token concurrency
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

# No global lock — each client has its own lock
# from services.ai_lock import ai_lock

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config (Railway env vars)
# ---------------------------------------------------------------------------
BASE_URL = "https://chat.qwen.ai"

QWEN_MODEL = os.getenv("QWEN_MODEL", "").strip() or "qwen-latest-series-invite-beta-v24"
QWEN_THINKING = os.getenv("QWEN_THINKING_MODE", "").strip() or "Thinking"

# Kept for backward compatibility
CHAT_URL = BASE_URL
REFRESH_URL = ""

print(f"🌐 qwen_ai: direct reverse API → {BASE_URL}")
print(f"[qwen_ai] model={QWEN_MODEL!r} thinking={QWEN_THINKING!r}")

# ---------------------------------------------------------------------------
# Reverse API helpers
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
    try:
        import oss2
    except ImportError:
        logger.warning("[qwen] oss2 not installed — image upload skipped")
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
                    thoughts = extra.get("summary_thought", {}).get("content", [])
                    if thoughts:
                        full_thoughts = thoughts
                else:
                    if content_chunk:
                        full_reply += content_chunk

                if finish_reason == "stop":
                    break
    except Exception as e:
        logger.warning(f"[qwen] _send_stream error: {e}")

    return full_reply

# ---------------------------------------------------------------------------
# Training images
# ---------------------------------------------------------------------------
_SERVICES_DIR = os.path.dirname(os.path.abspath(__file__))
_TRAINING_IMAGES: List[str] = []

def _load_training_images() -> List[str]:
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
        print(f"📚 qwen_ai: {len(images)} training image(s) ready")
    else:
        print("⚠️  qwen_ai: no training images found in services/")
    return images

_TRAINING_IMAGES = _load_training_images()

# ---------------------------------------------------------------------------
# Chart generation
# ---------------------------------------------------------------------------
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_CHARTS = True
    print("📊 qwen_ai: matplotlib OK — charts enabled")
except ImportError:
    HAS_CHARTS = False
    print("⚠️ qwen_ai: matplotlib not found — text-only mode")

def _draw_chart(candles: list, symbol: str, tf: str) -> Optional[str]:
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

        ax1.set_title(f"{symbol} · {tf} · {n} candles", color="#e0e0e0", fontsize=10, pad=6)
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
        plt.savefig(buf, format="png", dpi=75, bbox_inches="tight", facecolor="#0d1117")
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
# System prompt (unchanged)
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
- Low volume candles near void — treat with caution

---
SESSION AWARENESS RULE:
- ASIA session: lower liquidity, more fake moves — require stronger void
- LONDON / NY_OPEN: high validity — voids in these sessions most reliable
- NY_AFTERNOON / ASIA_PRE: declining volume — be more selective

---
WICK + VOID DIRECTION RULE (CRITICAL):

- UP trend: use UPPER WICK voids, ignore lower wick voids
- DOWN trend: use LOWER WICK voids, ignore upper wick voids

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
- TP1 = nearest realistic target (1:1 to 1:2 R/R)
- TP2 = intermediate target (1:2 to 1:3 R/R)
- MAX = maximum realistic extension (1:3+ R/R or next major HTF level)
- For LONG: entry < tp1 < tp2 < tp_max
- For SHORT: entry > tp1 > tp2 > tp_max

---
TRAINING DATA (see attached images for visual patterns)
"""

# ---------------------------------------------------------------------------
# Single-token Qwen client with per-client lock
# ---------------------------------------------------------------------------

class QwenAIClient:
    """One bearer token = one independent Qwen API client with its own lock."""

    def __init__(self, token: str, slot: int):
        self.token = token
        self.slot = slot
        self._tag = f"[QW-{slot}]"
        self.exhausted = False
        self.client = httpx.AsyncClient(timeout=240)
        self._lock = asyncio.Lock()   # 🔒 Per-client lock untuk mencegah concurrent usage of same token

    async def _refresh(self) -> bool:
        return False

    async def analyze(
        self,
        symbol: str,
        candles_by_tf: dict,
        current_price: float = None,
        backend_context: dict = None,
    ) -> dict:
        """Analyze one symbol. This method is serialized per token via self._lock."""
        async with self._lock:   # 🔒 Ensure only one task uses this token at a time
            return await self._analyze_unsafe(symbol, candles_by_tf, current_price, backend_context)

    async def _analyze_unsafe(
        self,
        symbol: str,
        candles_by_tf: dict,
        current_price: float = None,
        backend_context: dict = None,
    ) -> dict:
        tag = self._tag
        logger.info(f"{tag} Starting analysis for {symbol}")

        # Generate charts
        loop = asyncio.get_event_loop()
        charts: Dict[str, str] = {}
        try:
            charts = await loop.run_in_executor(None, _generate_all_charts, candles_by_tf, symbol)
            if charts:
                print(f"{tag} 📊 {symbol} charts ready: {list(charts.keys())}")
        except Exception as e:
            logger.warning(f"{tag} Chart generation error: {e}")

        # Build OHLCV text blocks
        tf_blocks = []
        last_candle_price = None
        for tf in ["5m", "15m", "30m", "1h", "4h"]:
            candles = candles_by_tf.get(tf, [])
            if not candles:
                continue
            lines = [f"=== {symbol} | {tf} | last {min(len(candles), 150)} candles ===",
                     "timestamp, open, high, low, close, volume"]
            for c in candles[-150:]:
                lines.append(f"{c[0]}, {c[1]}, {c[2]}, {c[3]}, {c[4]}, {c[5]}")
            tf_blocks.append("\n".join(lines))
            last_candle_price = float(candles[-1][4])

        live_price = current_price if (current_price and current_price > 0) else last_candle_price
        ohlcv_text = "\n\n".join(tf_blocks) if tf_blocks else "No candle data available."

        # Backend context block
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
━━━ BACKEND PRE-COMPUTED CONTEXT ━━━
 Session: {session}
 Allow Reversal: {"YES" if allow_reversal else "NO"}

 Market Structure:
{ms_lines}

 Swing Points:
{swing_text}

 Volume Delta:
{vd_lines}

 ATR:
{atr_lines}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

        # Training images block
        n_training = len(_TRAINING_IMAGES)
        n_charts = len(charts)
        training_img_block = ""
        if n_training > 0:
            training_img_block = f"---\nTRAINING REFERENCE IMAGES ({n_training} images attached)\n"
        chart_img_block = ""
        if n_charts > 0:
            chart_img_block = f"---\nLIVE CANDLESTICK CHARTS ({n_charts} images: {', '.join(charts.keys())})\n"

        prompt_text = f"""Analyze {symbol}

{ohlcv_text}

{training_img_block}
{chart_img_block}
{backend_block}
⚠️ CURRENT REALTIME PRICE: {live_price}

---
VOID POSITION RULE:
- LONG → void MUST be BELOW current price ({live_price})
- SHORT → void MUST be ABOVE current price ({live_price})
- If void is on wrong side → IGNORE
- If no valid void → NO TRADE

ENTRY DIRECTION RULE:
- LONG → entry MUST be BELOW {live_price}
- SHORT → entry MUST be ABOVE {live_price}

---
Respond in EXACT JSON format ONLY:

{{
  "trend": "UP" or "DOWN" or "SIDEWAYS",
  "pattern": "brief description",
  "decision": "LONG" or "SHORT" or "NO TRADE",
  "entry": <number>,
  "tp1": <number>,
  "tp2": <number>,
  "tp_max": <number>,
  "sl": <number>,
  "invalidation": <number>,
  "reason": "explanation",
  "confidence": <0-100>
}}

TP RULES: entry < tp1 < tp2 < tp_max for LONG; reverse for SHORT.
If no clear void setup → NO TRADE."""

        # Upload images
        uploaded_files = []
        if _TRAINING_IMAGES:
            print(f"{tag} 📤 Uploading {len(_TRAINING_IMAGES)} training images...")
            for i, img_b64 in enumerate(_TRAINING_IMAGES):
                uf = await _upload_image_bytes(
                    self.token, base64.b64decode(img_b64),
                    f"training{i+1}.jpg", "image/jpeg", self.client
                )
                if uf:
                    uploaded_files.append(uf)
        for tf, img_b64 in charts.items():
            uf = await _upload_image_bytes(
                self.token, base64.b64decode(img_b64),
                f"chart_{symbol}_{tf}.png", "image/png", self.client
            )
            if uf:
                uploaded_files.append(uf)

        full_prompt = SYSTEM_PROMPT + "\n\n---\n\n" + prompt_text
        full_text = ""

        for attempt in range(2):
            try:
                print(f"{tag} Qwen request for {symbol} (attempt {attempt+1})")
                chat_id = await _create_chat(self.token, self.client)
                if not chat_id:
                    if attempt == 0:
                        continue
                    return self._no_trade("Failed to create chat")

                raw_reply = await _send_stream(self.token, chat_id, full_prompt, self.client, uploaded_files or None)
                await _delete_chat(self.token, chat_id, self.client)

                if raw_reply:
                    import re
                    full_text = re.sub(r"<think>.*?</think>", "", raw_reply, flags=re.DOTALL).strip()
                    break
                if attempt == 0:
                    continue
                return self._no_trade("Empty response")
            except Exception as e:
                logger.error(f"{tag} Request exception: {e}")
                return self._no_trade(f"Request error: {e}")

        if not full_text.strip():
            return self._no_trade("Empty AI response")

        start = full_text.find("{")
        end = full_text.rfind("}") + 1
        if start < 0 or end <= start:
            return self._no_trade("No JSON in response")

        json_str = full_text[start:end]
        try:
            result = json.loads(json_str)
        except json.JSONDecodeError as je:
            logger.error(f"{tag} JSON decode error: {je}")
            return self._no_trade(f"JSON parse error: {je}")

        decision = result.get("decision", "NO TRADE").upper().strip()
        if decision not in ("LONG", "SHORT", "NO TRADE"):
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
            "original_prompt": full_prompt,
            "original_ai_response": full_text,
        }

        print(f"{tag} ✅ {symbol} → {decision} entry={parsed['entry']} conf={parsed['confidence']}%")
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
# Parallel wrapper with per-token locks
# ---------------------------------------------------------------------------

class ParallelQwenAI:
    def __init__(self):
        self.clients: List[QwenAIClient] = []
        self._rr_idx = 0

        for slot in range(1, 6):
            token = os.getenv(f"QWEN_TOKEN_{slot}", "").strip()
            if token:
                self.clients.append(QwenAIClient(token=token, slot=slot))
                print(f"[ParallelQwen] ✅ Token slot {slot} loaded")

        if not self.clients:
            print("[ParallelQwen] ❌ No Qwen tokens found! Set QWEN_TOKEN_1 at minimum.")
        else:
            print(f"[ParallelQwen] {len(self.clients)} token(s) | model={QWEN_MODEL} | charts={'ON' if HAS_CHARTS else 'OFF'}")

    def reload_tokens(self):
        from services.token_manager import token_manager

        for client in self.clients:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(client.close())
            except Exception:
                pass

        self.clients = []
        self._rr_idx = 0
        for slot, token in enumerate(token_manager.get_tokens(), 1):
            if token:
                self.clients.append(QwenAIClient(token=token, slot=slot))
                print(f"[ParallelQwen] 🔄 Token slot {slot} reloaded")
        print(f"[ParallelQwen] reload_tokens: {len(self.clients)} active token(s)")

    def _available_clients(self) -> list:
        available = [c for c in self.clients if not c.exhausted]
        if not available:
            print("[ParallelQwen] All tokens exhausted — resetting")
            for c in self.clients:
                c.exhausted = False
            available = self.clients
        return available

    _ROTATE_REASONS = ("RateLimited", "HTTP 502")

    def _should_rotate(self, reason: str) -> bool:
        return any(r in reason for r in self._ROTATE_REASONS)

    async def analyze_parallel(self, items: list, max_concurrent: int = 3) -> list:
        """
        Process multiple symbols in parallel using different tokens.
        Items: list of tuples (symbol, candles_by_tf, current_price, backend_context)
        Returns list of dict results in same order.
        """
        if not self.clients:
            return [self._no_trade("No tokens configured")] * len(items)

        # Round‑robin assign items to clients (ensuring each client gets at most one task if enough tokens)
        # But we will use a semaphore to limit total concurrency, and assign each task to a specific client
        # based on round‑robin.
        sem = asyncio.Semaphore(max_concurrent)

        async def process_with_client(idx, item):
            async with sem:
                client_idx = idx % len(self.clients)
                client = self.clients[client_idx]
                sym, tfs, price, bctx = item
                print(f"[Parallel] {sym} → using token slot {client.slot}")
                try:
                    result = await client.analyze(sym, tfs, price, bctx)
                except Exception as e:
                    result = self._no_trade(f"Exception: {e}")
                # If rotate-needed, try another token once
                if self._should_rotate(result.get("reason", "")):
                    alt_idx = (client_idx + 1) % len(self.clients)
                    alt_client = self.clients[alt_idx]
                    print(f"[Parallel] {sym} rotate → token slot {alt_client.slot}")
                    try:
                        result = await alt_client.analyze(sym, tfs, price, bctx)
                    except Exception as e:
                        result = self._no_trade(f"Retry failed: {e}")
                return result

        tasks = [process_with_client(i, item) for i, item in enumerate(items)]
        results = await asyncio.gather(*tasks)
        return results

    async def analyze(
        self,
        symbol: str,
        candles_by_tf: dict,
        current_price: float = None,
        backend_context: dict = None,
    ) -> dict:
        """Single symbol analysis using round‑robin token, with per‑token lock handled inside client."""
        if not self.clients:
            return self._no_trade("No tokens configured")

        # Round‑robin pick a client
        client = self.clients[self._rr_idx % len(self.clients)]
        self._rr_idx += 1

        result = await client.analyze(symbol, candles_by_tf, current_price, backend_context)

        if self._should_rotate(result.get("reason", "")):
            # Try next token
            alt_client = self.clients[self._rr_idx % len(self.clients)]
            self._rr_idx += 1
            print(f"[QwenAI] Retry {symbol} → slot {alt_client.slot}")
            result = await alt_client.analyze(symbol, candles_by_tf, current_price, backend_context)

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
