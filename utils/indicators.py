"""
Indicator calculations for scalping bot.
"""
from typing import List, Optional


def compute_ema(closes: List[float], period: int) -> List[float]:
    ema = []
    k = 2 / (period + 1)
    for i, c in enumerate(closes):
        if i == 0:
            ema.append(c)
        else:
            ema.append(c * k + ema[-1] * (1 - k))
    return ema


def compute_rsi(closes: List[float], period: int = 14) -> List[Optional[float]]:
    if len(closes) <= period:
        return [None] * len(closes)

    rsi = [None] * period
    diffs = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in diffs]
    losses = [max(-d, 0) for d in diffs]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(closes)):
        if avg_loss == 0:
            rsi.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi.append(100 - 100 / (1 + rs))
        if i < len(closes) - 1:
            idx = i  # diffs[i] corresponds to closes[i+1]-closes[i]
            g = gains[idx]
            l = losses[idx]
            avg_gain = (avg_gain * (period - 1) + g) / period
            avg_loss = (avg_loss * (period - 1) + l) / period

    return rsi


def compute_parabolic_sar(highs: List[float], lows: List[float],
                           af_start=0.02, af_step=0.02, af_max=0.2) -> List[Optional[float]]:
    if len(highs) < 2:
        return [None] * len(highs)

    sar = [None] * len(highs)
    bull = True
    ep = highs[0]
    af = af_start
    sar[0] = lows[0]

    for i in range(1, len(highs)):
        prev_sar = sar[i - 1]
        new_sar = prev_sar + af * (ep - prev_sar)

        if bull:
            new_sar = min(new_sar, lows[i - 1], lows[i - 2] if i > 1 else lows[i - 1])
            if lows[i] < new_sar:
                bull = False
                new_sar = ep
                ep = lows[i]
                af = af_start
            else:
                if highs[i] > ep:
                    ep = highs[i]
                    af = min(af + af_step, af_max)
        else:
            new_sar = max(new_sar, highs[i - 1], highs[i - 2] if i > 1 else highs[i - 1])
            if highs[i] > new_sar:
                bull = True
                new_sar = ep
                ep = highs[i]
                af = af_start
            else:
                if lows[i] < ep:
                    ep = lows[i]
                    af = min(af + af_step, af_max)

        sar[i] = new_sar

    return sar


def compute_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[Optional[float]]:
    if len(highs) < 2:
        return [None] * len(highs)
    trs = [None]
    for i in range(1, len(highs)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    atr = [None] * period
    valid = [t for t in trs[1:] if t is not None]
    if len(valid) < period:
        return [None] * len(highs)
    atr_val = sum(valid[:period]) / period
    atr.append(atr_val)
    for i in range(period + 1, len(trs)):
        atr_val = (atr_val * (period - 1) + trs[i]) / period
        atr.append(atr_val)
    return atr


def compute_adx(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Optional[float]:
    """Return last ADX value (0-100). >25 = trending, <20 = weak."""
    if len(highs) < period * 2 + 2:
        return None
    plus_dm, minus_dm, trs = [], [], []
    for i in range(1, len(highs)):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if up > down and up > 0 else 0)
        minus_dm.append(down if down > up and down > 0 else 0)
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    def _smooth(values, p):
        s = sum(values[:p])
        result = [s]
        for v in values[p:]:
            s = s - s / p + v
            result.append(s)
        return result
    sm_tr = _smooth(trs, period)
    sm_plus = _smooth(plus_dm, period)
    sm_minus = _smooth(minus_dm, period)
    dx_list = []
    for i in range(len(sm_tr)):
        if sm_tr[i] == 0:
            continue
        di_plus = 100 * sm_plus[i] / sm_tr[i]
        di_minus = 100 * sm_minus[i] / sm_tr[i]
        dsum = di_plus + di_minus
        dx_list.append(100 * abs(di_plus - di_minus) / dsum if dsum else 0)
    if len(dx_list) < period:
        return None
    adx = sum(dx_list[:period]) / period
    for dx in dx_list[period:]:
        adx = (adx * (period - 1) + dx) / period
    return round(adx, 2)


def compute_cvd_summary(candles: list) -> dict:
    """
    Approximate Cumulative Volume Delta from OHLCV.
    Bull candle (close>=open) → delta = +volume, bear → delta = -volume.
    Returns last-N summary for context.
    """
    if not candles:
        return {"cvd_last_20": 0, "delta_last_5": 0, "buyer_pressure": "neutral"}
    recent = candles[-20:]
    cvd = 0.0
    for c in recent:
        try:
            o, cl, vol = float(c[1]), float(c[4]), float(c[5])
        except (IndexError, ValueError):
            continue
        cvd += vol if cl >= o else -vol
    last5 = candles[-5:]
    d5 = 0.0
    for c in last5:
        try:
            o, cl, vol = float(c[1]), float(c[4]), float(c[5])
        except (IndexError, ValueError):
            continue
        d5 += vol if cl >= o else -vol
    if cvd > 0 and d5 > 0:
        pressure = "bullish"
    elif cvd < 0 and d5 < 0:
        pressure = "bearish"
    elif abs(cvd) < abs(d5) * 0.5:
        pressure = "divergence"
    else:
        pressure = "neutral"
    return {
        "cvd_last_20": round(cvd, 2),
        "delta_last_5": round(d5, 2),
        "buyer_pressure": pressure,
    }


def compute_swing_points(highs: List[float], lows: List[float], closes: List[float], lookback: int = 5) -> dict:
    """
    Detect last HH, HL, LH, LL from recent candles.
    Returns prices of each swing type.
    """
    if len(highs) < lookback * 2 + 1:
        return {"last_hh": None, "last_hl": None, "last_lh": None, "last_ll": None}
    pivot_highs, pivot_lows = [], []
    for i in range(lookback, len(highs) - lookback):
        if highs[i] == max(highs[i - lookback:i + lookback + 1]):
            pivot_highs.append(highs[i])
        if lows[i] == min(lows[i - lookback:i + lookback + 1]):
            pivot_lows.append(lows[i])
    last_hh = last_hl = last_lh = last_ll = None
    if len(pivot_highs) >= 2:
        last_hh = max(pivot_highs[-2], pivot_highs[-1]) if pivot_highs[-1] > pivot_highs[-2] else None
        last_lh = min(pivot_highs[-2], pivot_highs[-1]) if pivot_highs[-1] < pivot_highs[-2] else None
    if len(pivot_lows) >= 2:
        last_hl = max(pivot_lows[-2], pivot_lows[-1]) if pivot_lows[-1] > pivot_lows[-2] else None
        last_ll = min(pivot_lows[-2], pivot_lows[-1]) if pivot_lows[-1] < pivot_lows[-2] else None
    return {
        "last_hh": round(last_hh, 6) if last_hh else None,
        "last_hl": round(last_hl, 6) if last_hl else None,
        "last_lh": round(last_lh, 6) if last_lh else None,
        "last_ll": round(last_ll, 6) if last_ll else None,
    }


def classify_market_structure(highs: List[float], lows: List[float], closes: List[float], lookback: int = 5) -> str:
    """
    Classify trend from swing points: UP (HH+HL), DOWN (LH+LL), or RANGING.
    """
    swings = compute_swing_points(highs, lows, closes, lookback)
    has_hh = swings["last_hh"] is not None
    has_hl = swings["last_hl"] is not None
    has_lh = swings["last_lh"] is not None
    has_ll = swings["last_ll"] is not None
    if has_hh and has_hl:
        return "UP"
    elif has_lh and has_ll:
        return "DOWN"
    return "RANGING"


def compute_session() -> str:
    """Return current trading session based on UTC hour."""
    from datetime import datetime, timezone
    hour = datetime.now(timezone.utc).hour
    if 0 <= hour < 7:
        return "ASIA"
    elif 7 <= hour < 12:
        return "LONDON"
    elif 12 <= hour < 17:
        return "NY_OPEN"
    elif 17 <= hour < 21:
        return "NY_AFTERNOON"
    else:
        return "ASIA_PRE"


def compute_backend_context(candles_by_tf: dict) -> dict:
    """
    Compute full backend context for Analysis AI (entry decisions).
    Returns market_structure, swing_points, trend per timeframe,
    volume delta, session, and ATR info.
    """
    context = {
        "market_structure": {},
        "swing_points": {},
        "trend": {},
        "allow_reversal": True,
        "volume_delta": {},
        "session": compute_session(),
        "atr": {},
    }
    for tf, candles in candles_by_tf.items():
        if not candles or len(candles) < 20:
            continue
        highs = [float(c[2]) for c in candles]
        lows = [float(c[3]) for c in candles]
        closes = [float(c[4]) for c in candles]
        struct = classify_market_structure(highs, lows, closes)
        context["market_structure"][tf] = struct
        context["trend"][tf] = struct
        context["swing_points"][tf] = compute_swing_points(highs, lows, closes)
        context["volume_delta"][tf] = compute_cvd_summary(candles)
        atr_vals = compute_atr(highs, lows, closes)
        valid_atr = [v for v in atr_vals if v is not None]
        if valid_atr:
            context["atr"][tf] = round(valid_atr[-1], 6)
    # Determine allow_reversal: only if 4h or 1h structure is not strongly directional
    h4 = context["market_structure"].get("4h", "RANGING")
    h1 = context["market_structure"].get("1h", "RANGING")
    context["allow_reversal"] = not (h4 in ("UP", "DOWN") and h1 == h4)
    return context


def compute_position_backend_context(candles_by_tf: dict, direction: str, entry: float, tp1: float = None) -> dict:
    """
    Compute full backend context for Position AI (hold/close/sl+ decisions).
    Includes thesis_score, momentum, swing_structure, atr_context, session, volume_delta, liquidity_sweep.
    """
    ctx = {
        "session": compute_session(),
        "volume_delta": {},
        "momentum": {},
        "swing_structure": {},
        "atr_context": {},
        "thesis_score": {},
        "liquidity_sweep": {},
    }
    for tf, candles in candles_by_tf.items():
        if not candles or len(candles) < 20:
            continue
        highs = [float(c[2]) for c in candles]
        lows = [float(c[3]) for c in candles]
        closes = [float(c[4]) for c in candles]
        volumes = [float(c[5]) for c in candles]
        struct = classify_market_structure(highs, lows, closes)
        ctx["swing_structure"][tf] = {
            **compute_swing_points(highs, lows, closes),
            "structure": struct,
            "micro_break": _detect_micro_break(highs, lows, closes, direction),
        }
        ctx["volume_delta"][tf] = compute_cvd_summary(candles)
        atr_vals = compute_atr(highs, lows, closes)
        valid_atr = [v for v in atr_vals if v is not None]
        if valid_atr:
            last_atr = valid_atr[-1]
            current_price = closes[-1]
            pullback = abs(current_price - entry)
            ctx["atr_context"][tf] = {
                "atr": round(last_atr, 6),
                "atr_normal_pullback": round(last_atr * 1.5, 6),
                "current_pullback": round(pullback, 6),
                "abnormal_move": pullback > last_atr * 2.5,
            }
        adx = compute_adx(highs, lows, closes)
        ctx["momentum"][tf] = {
            "adx": adx,
            "trend_strength": "strong" if adx and adx > 25 else ("weak" if adx and adx < 18 else "moderate"),
            "candle_velocity": _candle_velocity(closes),
        }
        ctx["liquidity_sweep"][tf] = _detect_liquidity_sweep(highs, lows, closes, direction)
    # thesis_score: backend scoring for position validity
    primary_tf_delta = ctx["volume_delta"].get("15m") or ctx["volume_delta"].get("5m") or {}
    primary_struct = ctx["swing_structure"].get("15m") or ctx["swing_structure"].get("5m") or {}
    primary_momentum = ctx["momentum"].get("15m") or ctx["momentum"].get("5m") or {}
    trend_intact = primary_struct.get("structure") in (
        ("UP" if direction == "LONG" else "DOWN"), "RANGING"
    ) and not primary_struct.get("micro_break", False)
    volume_support = (
        primary_tf_delta.get("buyer_pressure") == ("bullish" if direction == "LONG" else "bearish")
        or primary_tf_delta.get("buyer_pressure") == "neutral"
    )
    momentum_shift = primary_momentum.get("trend_strength") == "weak"
    structure_break = primary_struct.get("micro_break", False)
    ctx["thesis_score"] = {
        "trend_intact": trend_intact,
        "volume_support": volume_support,
        "momentum_shift": momentum_shift,
        "structure_break": structure_break,
        "score": sum([trend_intact, volume_support, not momentum_shift, not structure_break]),
    }
    return ctx


def _detect_micro_break(highs, lows, closes, direction):
    """Detect if recent candles broke the most recent swing low (LONG) or swing high (SHORT)."""
    if len(closes) < 10:
        return False
    recent_high = max(highs[-10:-2])
    recent_low = min(lows[-10:-2])
    last_close = closes[-1]
    if direction == "LONG" and last_close < recent_low:
        return True
    if direction == "SHORT" and last_close > recent_high:
        return True
    return False


def _candle_velocity(closes):
    """Average absolute candle-to-candle change over last 5 candles."""
    if len(closes) < 6:
        return 0
    changes = [abs(closes[i] - closes[i - 1]) for i in range(-5, 0)]
    return round(sum(changes) / len(changes), 6)


def _detect_liquidity_sweep(highs, lows, closes, direction):
    """
    Detect if a liquidity sweep just occurred.
    For LONG: price swept below recent low then recovered.
    For SHORT: price swept above recent high then rejected.
    """
    if len(closes) < 5:
        return {"detected": False, "type": None}
    prev_low = min(lows[-6:-2])
    prev_high = max(highs[-6:-2])
    last_low = lows[-1]
    last_high = highs[-1]
    last_close = closes[-1]
    if direction == "LONG" and last_low < prev_low and last_close > prev_low:
        return {"detected": True, "type": "sweep_low_recovery"}
    if direction == "SHORT" and last_high > prev_high and last_close < prev_high:
        return {"detected": True, "type": "sweep_high_rejection"}
    return {"detected": False, "type": None}


def compute_all(candles: list) -> dict:
    """
    Compute all indicators from candle data.
    candles: [[timestamp, open, high, low, close, volume], ...]
    """
    opens = [float(c[1]) for c in candles]
    highs = [float(c[2]) for c in candles]
    lows = [float(c[3]) for c in candles]
    closes = [float(c[4]) for c in candles]

    ema9 = compute_ema(closes, 9)
    ema21 = compute_ema(closes, 21)
    rsi = compute_rsi(closes, 14)
    psar = compute_parabolic_sar(highs, lows)

    trend = "BULLISH" if ema9[-1] > ema21[-1] else "BEARISH"

    return {
        "ema9": ema9,
        "ema21": ema21,
        "rsi": rsi,
        "psar": psar,
        "ema9_last": round(ema9[-1], 4),
        "ema21_last": round(ema21[-1], 4),
        "rsi_last": round(rsi[-1], 2) if rsi[-1] is not None else None,
        "psar_last": round(psar[-1], 4) if psar[-1] is not None else None,
        "current_price": closes[-1],
        "trend": trend,
    }


def format_ohlcv_text(candles: list, limit: int = 50) -> str:
    """Format OHLCV data as readable text for AI prompt."""
    recent = candles[-limit:]
    lines = ["timestamp, open, high, low, close, volume"]
    for c in recent:
        lines.append(f"{c[0]}, {c[1]}, {c[2]}, {c[3]}, {c[4]}, {c[5]}")
    return "\n".join(lines)


def calculate_position_size(balance: float, leverage: float, price: float,
                              mode: str = "ALL_IN", manual_margin: float = None,
                              volume_place: int = 3,
                              safety_factor: float = 0.95) -> str:
    """
    Calculate order size.
    mode: ALL_IN or MANUAL
    safety_factor: fraction of balance to use (default 0.95 = 95%) to reserve
                   room for fees and avoid 'exceeds balance' errors.
    For MANUAL mode, if manual_margin > available balance it is capped at
    balance * safety_factor so the order never exceeds what the account holds.
    """
    if mode == "MANUAL" and manual_margin is not None:
        # Cap manual margin so it never exceeds available balance
        max_margin = balance * safety_factor
        margin = min(float(manual_margin), max_margin)
    else:
        # ALL_IN: use most of the balance but keep a fee buffer
        margin = balance * safety_factor

    notional = margin * leverage
    size = notional / price
    return str(round(size, volume_place))
