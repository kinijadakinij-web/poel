"""
Bot engine — perpetual signal scanner (Multi-user support).
"""
import asyncio
import json
import logging
import os
import random
import sqlite3
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from services.mexc_client import mexc_client
from services.virtual_exchange import virtual_exchange
from services.qwen_ai import qwen_ai
from services.mexc_price_feed import price_feed
from services.position_ai import position_ai, MONITOR_INTERVAL
from services.database import db_save_signal, db_get_signals, db_delete_signals_by_user

logger = logging.getLogger(__name__)

TIMEFRAMES = ["5m", "15m", "30m", "1h", "4h"]
CANDLE_LIMIT = 150
TIMEFRAMES_MONITOR = ["5m", "15m", "1h", "4h"]

MAX_SIGNALS = 500
MAX_ACTIVE_SIGNALS = int(os.getenv("MAX_ACTIVE_SIGNALS", "20"))

REQUIRED_SYMBOLS = ["BTC_USDT", "ETH_USDT", "SOL_USDT"]
INTER_SYMBOL_DELAY = float(os.getenv("INTER_SYMBOL_DELAY", "2.0"))

KEEPALIVE_URL = os.getenv("KEEPALIVE_URL", "")
KEEPALIVE_INTERVAL = int(os.getenv("KEEPALIVE_INTERVAL", "240"))


class BotEngine:
    def __init__(self, user_id: Optional[str] = None):
        self.user_id = user_id
        self.running = False
        self.config: Dict[str, Any] = {}
        self.state = {
            "status": "IDLE",
            "last_signal": None,
            "last_error": None,
            "signals": [],
            "trade_count": 0,
            "win_count": 0,
            "loss_count": 0,
            "no_trade_count": 0,
            "total_pnl_pct": 0.0,
            "total_pnl_usdt": 0.0,
            "current_symbol": None,
            "symbols_scanned": 0,
            "active_signal_count": 0,
        }
        self._rebuild_counters()

        self._task: Optional[asyncio.Task] = None
        self._ka_task: Optional[asyncio.Task] = None
        self._listeners: List[Callable] = []

        self._pass_scanned: set = set()
        self._active_ids: set = set()

    def _rebuild_counters(self):
        """
        Rebuild in-memory counters dari DB.
        SELALU reset counter dulu sebelum hitung ulang supaya
        tidak double-count kalau dipanggil lebih dari sekali.
        """
        try:
            all_signals = db_get_signals(user_id=self.user_id, limit=MAX_SIGNALS)
        except sqlite3.OperationalError as e:
            if "no such table" in str(e).lower():
                logger.warning("Signals table not found — skipping counter rebuild")
                all_signals = []
            else:
                raise

        # ── Reset semua counter dulu ──
        self.state["trade_count"]     = 0
        self.state["win_count"]       = 0
        self.state["loss_count"]      = 0
        self.state["total_pnl_pct"]   = 0.0
        self.state["total_pnl_usdt"]  = 0.0
        self.state["signals"]         = []

        for s in all_signals:
            result = s.get("result")
            status = s.get("status")

            # ── Win: TP atau AI_CLOSE dengan pnl >= 0 ──
            if result == "TP" or (result == "AI_CLOSE" and (s.get("pnl_pct") or 0) >= 0):
                self.state["trade_count"] += 1
                self.state["win_count"]   += 1
                self.state["total_pnl_pct"]  = round(
                    self.state["total_pnl_pct"]  + (s.get("pnl_pct")  or 0), 4)
                self.state["total_pnl_usdt"] = round(
                    self.state["total_pnl_usdt"] + (s.get("pnl_usdt") or 0), 4)

            # ── Loss: SL atau AI_CLOSE dengan pnl < 0 ──
            elif result == "SL" or (result == "AI_CLOSE" and (s.get("pnl_pct") or 0) < 0):
                self.state["trade_count"] += 1
                self.state["loss_count"]  += 1
                self.state["total_pnl_pct"]  = round(
                    self.state["total_pnl_pct"]  + (s.get("pnl_pct")  or 0), 4)
                self.state["total_pnl_usdt"] = round(
                    self.state["total_pnl_usdt"] + (s.get("pnl_usdt") or 0), 4)

            # ── Masih OPEN → masuk active list ──
            elif status == "OPEN":
                self.state["signals"].append(s)

            # result TIMEOUT / INVALIDATED / CANCELLED → skip (bukan trade)

        self.state["signals"] = self.state["signals"][:MAX_SIGNALS]
        self.state["active_signal_count"] = len(self.state["signals"])

    def add_listener(self, fn: Callable):
        if fn not in self._listeners:
            self._listeners.append(fn)

    def _emit(self, event: str, data: Any):
        for fn in self._listeners:
            try:
                fn(event, data)
            except Exception:
                pass

    def _active_count(self) -> int:
        return sum(1 for s in self.state["signals"] if s.get("status") == "OPEN")

    async def start(self, config: dict):
        if self.running:
            return {"ok": False, "reason": "Bot already running"}

        # ── PROCESS OPEN SIGNALS FROM PREVIOUS SESSION ──
        try:
            old_signals = db_get_signals(user_id=self.user_id, status="OPEN")
            cleared = 0
            resumed = 0
            pending_resumed = 0
            now = int(time.time() * 1000)

            for sig in old_signals:
                age_ms = now - sig.get("timestamp", 0)
                entry_hit = bool(sig.get("entry_hit"))

                if entry_hit:
                    # Signal sudah entry → resume monitor
                    if not self._find_signal(sig["id"]):
                        self.state["signals"].insert(0, sig)
                    self._active_ids.add(sig["id"])
                    asyncio.create_task(self._monitor_signal(sig["id"]))
                    resumed += 1

                elif age_ms > 1800000:
                    # Pending > 30 menit, belum entry → cancel
                    sig["status"] = "CANCELLED"
                    sig["result"] = "CANCELLED"
                    sig["reason"] = "Stale signal cleared on bot restart"
                    db_save_signal(sig)
                    cleared += 1

                else:
                    # Pending < 30 menit, belum entry → resume monitor (masih fresh)
                    if not self._find_signal(sig["id"]):
                        self.state["signals"].insert(0, sig)
                    self._active_ids.add(sig["id"])
                    asyncio.create_task(self._monitor_signal(sig["id"]))
                    pending_resumed += 1

            if cleared > 0:
                print(f"[BotEngine] Cleared {cleared} stale pending signals")
            if resumed > 0:
                print(f"[BotEngine] Resumed {resumed} active (entry_hit) signals")
            if pending_resumed > 0:
                print(f"[BotEngine] Resumed {pending_resumed} pending (waiting entry) signals")

            # Rebuild counters SETELAH proses signal lama
            # _rebuild_counters() reset & hitung ulang dari DB supaya tidak double count
            self._rebuild_counters()

        except Exception as e:
            print(f"[BotEngine] Could not process old signals: {e}")

        await price_feed.start()
        self.config = config
        self.running = True
        self.state["status"] = "RUNNING"
        self._task = asyncio.create_task(self._loop())

        if KEEPALIVE_URL:
            self._ka_task = asyncio.create_task(self._keepalive_loop())
            print(f"🏓 Keepalive ping started → {KEEPALIVE_URL} every {KEEPALIVE_INTERVAL}s")
        else:
            print("⚠️ KEEPALIVE_URL not set — Railway may sleep.")

        return {"ok": True}

    async def stop(self):
        """
        Stop HANYA scanner loop (_loop).
        Monitor tasks untuk signal yang sudah OPEN tetap jalan —
        mereka akan terus mantau TP/SL/AI decision sampai signal closed.
        Price feed WS juga tetap hidup supaya monitor bisa dapat harga.
        """
        self.running = False

        # Stop scanner loop
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        # Stop keepalive
        if self._ka_task:
            self._ka_task.cancel()
            try:
                await self._ka_task
            except asyncio.CancelledError:
                pass
            self._ka_task = None

        self.state["status"] = "IDLE"
        print("[BotEngine] Scanner stopped. Active signal monitors still running.")
        return {"ok": True}

    async def shutdown(self):
        """
        Full shutdown — dipanggil saat app mati (Railway restart/deploy).
        Stop scanner + cleanup resource. Monitor tasks akan mati sendiri
        karena event loop ikut mati.
        """
        await self.stop()
        await price_feed.stop()
        await mexc_client.close()
        await qwen_ai.close()
        await position_ai.close()

    async def _keepalive_loop(self):
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            while self.running:
                try:
                    await asyncio.sleep(KEEPALIVE_INTERVAL)
                    r = await client.get(KEEPALIVE_URL)
                    print(f"🏓 Keepalive ping → {r.status_code}")
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    print(f"🏓 Keepalive ping failed: {e}")

    async def _loop(self):
        logger.info("Bot scanner loop started")
        print("Bot scanner loop started")

        await asyncio.sleep(2)

        while self.running:
            try:
                active = self._active_count()

                if active >= MAX_ACTIVE_SIGNALS:
                    self.state["status"] = "MONITORING"
                    self._emit("status",
                        f"At cap ({active}/{MAX_ACTIVE_SIGNALS} active signals). "
                        "Waiting for a signal to close…"
                    )
                    await asyncio.sleep(10)
                    continue

                slots_needed = MAX_ACTIVE_SIGNALS - active
                print(f"\n[Loop] Active={active}/{MAX_ACTIVE_SIGNALS} — scanning for {slots_needed} more signal(s)")

                pool = await self._build_pool(exclude=self._pass_scanned)

                if not pool:
                    print("[Loop] Pass exhausted — resetting scanned set for next pass")
                    self._pass_scanned = set()
                    await asyncio.sleep(5)
                    continue

                self.state["status"] = "RUNNING"

                for sym in pool:
                    if not self.running:
                        break
                    if self._active_count() >= MAX_ACTIVE_SIGNALS:
                        break

                    print(f"\n[Scan] {sym}")
                    self._emit("status", f"Scanning: {sym}")

                    # Fetch market data untuk simbol ini (timeframes tetap paralel — beda endpoint)
                    mresult = await self._fetch_market_data(sym)
                    self._pass_scanned.add(sym)

                    if mresult is None:
                        await asyncio.sleep(INTER_SYMBOL_DELAY)
                        continue

                    candles_by_tf, current_price = mresult
                    if not candles_by_tf or current_price <= 0:
                        await asyncio.sleep(INTER_SYMBOL_DELAY)
                        continue

                    # Analisis AI — 1 simbol, 1 token, sequential
                    print(f" Sending AI request for {sym}…")
                    signal = await qwen_ai.analyze(sym, candles_by_tf, current_price)

                    found = self._process_signal(sym, current_price, signal)
                    if found:
                        self._emit("progress", {
                            "active_signal_count": self._active_count(),
                            "max_active_signals": MAX_ACTIVE_SIGNALS,
                            "symbols_scanned": self.state["symbols_scanned"],
                        })
                    if self._active_count() >= MAX_ACTIVE_SIGNALS:
                        break

                    await asyncio.sleep(INTER_SYMBOL_DELAY)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Bot loop error: {e}", exc_info=True)
                self.state["last_error"] = str(e)
                self._emit("error", str(e))
                await asyncio.sleep(30)

        logger.info("Bot scanner loop ended")

    async def _fetch_market_data(self, symbol: str):
        candles_by_tf: Dict[str, list] = {}
        for tf in TIMEFRAMES:
            try:
                candles = await mexc_client.get_candles(symbol, tf, CANDLE_LIMIT)
                if candles and len(candles) >= 5:
                    candles_by_tf[tf] = candles
            except Exception as e:
                logger.debug(f" {symbol}/{tf} fetch error: {e}")

        if not candles_by_tf:
            return None

        try:
            ticker = await mexc_client.get_ticker(symbol)
            current_price = float(ticker.get("lastPr", ticker.get("last", 0)) or 0)
        except Exception:
            tf_any = next(iter(candles_by_tf.values()))
            current_price = float(tf_any[-1][4])

        if current_price <= 0:
            return None

        return candles_by_tf, current_price

    async def _build_pool(self, exclude: set = None) -> List[str]:
        exclude = exclude or set()
        self._emit("status", "Fetching contract list from MEXC…")
        try:
            contracts = await mexc_client.get_contracts()
        except Exception as e:
            logger.error(f"Failed to fetch MEXC contracts: {e}")
            self._emit("error", f"Contract fetch error: {e}")
            return [s for s in REQUIRED_SYMBOLS if s not in exclude]

        all_symbols = [c["symbol"] for c in contracts if c.get("symbol")]
        mandatory = [s for s in REQUIRED_SYMBOLS
                     if s in all_symbols and s not in exclude]
        pool = [s for s in all_symbols
                if s not in REQUIRED_SYMBOLS and s not in exclude]
        random.shuffle(pool)

        return mandatory + pool

    def _process_signal(self, symbol: str, current_price: float, signal: dict) -> bool:
        self.state["current_symbol"] = symbol
        self.state["symbols_scanned"] += 1

        decision = signal.get("decision", "NO TRADE")

        if decision == "NO TRADE":
            self.state["no_trade_count"] += 1
            print(f" {symbol} → NO TRADE")
            return False

        sig_id = str(uuid.uuid4())[:8]
        signal_record = {
            "id": sig_id,
            "user_id": self.user_id,
            "symbol": symbol,
            "timestamp": int(time.time() * 1000),
            "current_price": current_price,
            "trend": signal.get("trend"),
            "pattern": signal.get("pattern"),
            "decision": decision,
            "entry": signal.get("entry"),
            "tp1": signal.get("tp1"),
            "tp2": signal.get("tp2"),
            "tp_max": signal.get("tp_max"),
            "tp": signal.get("tp1"),
            "sl": signal.get("sl"),
            "sl_trigger_price": signal.get("sl_trigger_price"),
            "invalidation": signal.get("invalidation"),
            "reason": signal.get("reason"),
            "confidence": signal.get("confidence"),
            "status": "OPEN",
            "result": None,
            "pnl_pct": None,
            "pnl_usdt": None,
            "closed_at": None,
            "closed_price": None,
            "entry_hit": False,
            "created_at": int(time.time()),
        }

        _entry = signal_record.get("entry") or current_price
        _tp = signal_record.get("tp")
        _sl = signal_record.get("sl")
        if _entry and _tp and _sl:
            try:
                e, t, s = float(_entry), float(_tp), float(_sl)
                invalid_long = (decision == "LONG" and not (t > e > s))
                invalid_short = (decision == "SHORT" and not (t < e < s))
                if invalid_long or invalid_short:
                    print(f" ⚠️ {symbol} {decision} REJECTED — invalid TP/SL: "
                          f"entry={e} tp={t} sl={s}")
                    return False
            except (TypeError, ValueError):
                pass

        self.state["signals"].insert(0, signal_record)
        self.state["signals"] = self.state["signals"][:MAX_SIGNALS]
        db_save_signal(signal_record)

        self.state["last_signal"] = signal_record
        self.state["active_signal_count"] = self._active_count()
        self._emit("signal", signal_record)

        print(
            f" ✅ {symbol} {decision} @ {current_price} | "
            f"TP1={signal.get('tp1')} TP2={signal.get('tp2')} MAX={signal.get('tp_max')} | "
            f"SL={signal.get('sl')} | conf={signal.get('confidence')}% "
            f"[active {self._active_count()}/{MAX_ACTIVE_SIGNALS}]"
        )

        price_feed.watch(symbol)
        asyncio.create_task(self._monitor_signal(sig_id))

        return True

    async def _monitor_signal(self, sig_id: str):
        signal = self._find_signal(sig_id)
        if not signal:
            return

        symbol = signal["symbol"]
        direction = signal["decision"]
        entry = float(signal.get("entry") or signal.get("current_price") or 0)
        tp = signal.get("tp")
        sl = signal.get("sl")
        inv_price = signal.get("invalidation")

        if not tp or not sl:
            price_feed.unwatch(symbol)
            return

        tp_f = float(tp)
        sl_f = float(sl)
        inv_f = float(inv_price) if inv_price else None

        original_analysis = {
            "trend": signal.get("trend"),
            "pattern": signal.get("pattern"),
            "reason": signal.get("reason"),
            "confidence": signal.get("confidence"),
        }

        max_duration = 60 * 60 * 8
        start = time.time()
        entry_hit = (entry <= 0)
        PRICE_TICK_INTERVAL = 3
        _last_tick_emit = start
        _last_ai_check = 0.0

        _start_price = float(signal.get("current_price") or entry)
        if entry > 0:
            _pullback_entry = (
                _start_price > entry if direction == "LONG" else _start_price < entry
            )
        else:
            _pullback_entry = False

        print(
            f" 🔍 {sig_id} monitor start (WS) | direction={direction} "
            f"entry={entry} start_price={_start_price} pullback={_pullback_entry}"
        )

        while time.time() - start < max_duration:
            # Catatan: self.running = False artinya SCANNER sudah stop,
            # tapi monitor ini tetap harus jalan sampai signal closed.
            # Yang break monitor hanya: signal closed/invalidated, timeout 8h,
            # atau task di-cancel (shutdown Railway).

            signal = self._find_signal(sig_id)
            if not signal or signal.get("status") == "CLOSED":
                break

            price = await price_feed.wait_for_price(symbol, timeout=5.0)
            if not price or price <= 0:
                try:
                    ticker = await mexc_client.get_ticker(symbol)
                    price = float(ticker.get("lastPr", ticker.get("last", 0)) or 0)
                except Exception:
                    continue
                if price <= 0:
                    continue

            signal["current_price"] = price

            now_t = time.time()
            if now_t - _last_tick_emit >= PRICE_TICK_INTERVAL:
                self._emit("price_tick", {
                    "id": sig_id,
                    "symbol": symbol,
                    "price": price,
                    "entry_hit": entry_hit,
                    "timestamp": int(now_t * 1000),
                })
                _last_tick_emit = now_t

            if inv_f and not entry_hit:
                inv_hit = (
                    (direction == "LONG" and price <= inv_f) or
                    (direction == "SHORT" and price >= inv_f)
                )
                if inv_hit:
                    signal.update({
                        "status": "INVALIDATED",
                        "result": "INVALIDATED",
                        "closed_at": int(time.time() * 1000),
                        "closed_price": price,
                        "pnl_usdt": 0.0,
                        "pnl_pct": 0.0,
                    })
                    db_save_signal(signal)
                    self.state["signals"] = [
                        s for s in self.state["signals"] if s["id"] != sig_id
                    ]
                    self.state["active_signal_count"] = self._active_count()
                    self._emit("signal_invalidated", {
                        "id": sig_id,
                        "symbol": symbol,
                        "price": price,
                        "timestamp": int(time.time() * 1000),
                    })
                    self._emit("balance_update", virtual_exchange.get_info(self.user_id))
                    print(f" ❌ {sig_id} INVALIDATED @ {price}"
                          f" [active {self._active_count()}/{MAX_ACTIVE_SIGNALS}]")
                    price_feed.unwatch(symbol)
                    break

            if not entry_hit:
                if direction == "LONG":
                    touched = price <= entry if _pullback_entry else price >= entry
                else:
                    touched = price >= entry if _pullback_entry else price <= entry

                if touched:
                    entry_hit = True
                    signal["entry_hit"] = True
                    _last_ai_check = time.time()
                    mode_label = "pullback" if _pullback_entry else "breakout"
                    print(f" 📍 {sig_id} entry HIT ({direction} {mode_label}) @ {price}")
                    db_save_signal(signal)
                else:
                    continue
                continue

            hit = None
            if direction == "LONG":
                if price >= tp_f: hit = "TP"
                elif price <= sl_f: hit = "SL"
            elif direction == "SHORT":
                if price <= tp_f: hit = "TP"
                elif price >= sl_f: hit = "SL"

            if hit:
                close_p = tp_f if hit == "TP" else sl_f
                pnl_pct = round(
                    (close_p - entry) / entry * 100 if direction == "LONG"
                    else (entry - close_p) / entry * 100, 4
                ) if entry > 0 else 0.0
                ve_label = "TP" if pnl_pct >= 0 else "SL"
                pnl_usdt = virtual_exchange.apply_result(ve_label, direction, entry, close_p, self.user_id)

                signal.update({
                    "status": "CLOSED",
                    "result": hit,
                    "pnl_pct": pnl_pct,
                    "pnl_usdt": pnl_usdt,
                    "closed_at": int(time.time() * 1000),
                    "closed_price": close_p,
                })
                self.state["trade_count"] += 1
                if pnl_pct >= 0:
                    self.state["win_count"] += 1
                else:
                    self.state["loss_count"] += 1
                self.state["total_pnl_pct"] = round(
                    self.state["total_pnl_pct"] + pnl_pct, 4)
                self.state["total_pnl_usdt"] = round(
                    self.state["total_pnl_usdt"] + pnl_usdt, 4)

                db_save_signal(signal)
                self.state["signals"] = [
                    s for s in self.state["signals"] if s["id"] != sig_id
                ]
                self.state["active_signal_count"] = self._active_count()
                self._emit("signal_closed", {**signal, "balance": virtual_exchange.get_info(self.user_id)["balance"]})
                self._emit("balance_update", virtual_exchange.get_info(self.user_id))
                print(
                    f" Signal {sig_id} {hit} @ {close_p} | "
                    f"pnl={pnl_pct}% / {pnl_usdt:+.4f} USDT | "
                    f"balance={virtual_exchange.get_info(self.user_id)['balance']} USDT | "
                    f"active {self._active_count()}/{MAX_ACTIVE_SIGNALS}"
                )
                price_feed.unwatch(symbol)
                break

            if (
                entry_hit
                and position_ai.enabled
                and (time.time() - _last_ai_check) >= MONITOR_INTERVAL
            ):
                _last_ai_check = time.time()
                print(f" 🤖 {sig_id} AI hold/close check ({symbol} {direction} @ {entry})…")

                try:
                    candles_by_tf: dict = {}
                    for tf in TIMEFRAMES_MONITOR:
                        try:
                            candles = await mexc_client.get_candles(symbol, tf, 100)
                            if candles and len(candles) >= 5:
                                candles_by_tf[tf] = candles
                        except Exception as e:
                            logger.debug(f" {sig_id} candle fetch {tf}: {e}")

                    if not candles_by_tf:
                        print(f" 🤖 {sig_id} no candle data — skipping AI check")
                        continue

                    ai_result = await position_ai.decide_with_retry(
                        symbol=symbol,
                        direction=direction,
                        entry=entry,
                        tp=tp_f,
                        sl=sl_f,
                        current_price=price,
                        candles_by_tf=candles_by_tf,
                        leverage=virtual_exchange.get_info(self.user_id)["leverage"],
                        margin_usdt=virtual_exchange.get_info(self.user_id)["entry_usdt"],
                        original_analysis=original_analysis,
                        sl_plus_history=signal.get("sl_plus_history") or [],
                        tp1=signal.get("tp1"),
                    )

                    signal["last_ai_decision"] = ai_result.get("decision")
                    signal["last_ai_reason"] = ai_result.get("reason")
                    signal["last_ai_at"] = int(time.time() * 1000)
                    db_save_signal(signal)

                    self._emit("signal_ai_update", {
                        "id": sig_id,
                        "symbol": symbol,
                        "decision": ai_result.get("decision"),
                        "reason": ai_result.get("reason"),
                        "new_sl": ai_result.get("new_sl"),
                        "timestamp": int(time.time() * 1000),
                    })

                    if ai_result.get("decision") == "SL+":
                        new_sl = ai_result.get("new_sl")
                        if new_sl and float(new_sl) > 0:
                            old_sl = sl_f
                            new_sl_f = float(new_sl)
                            sl_improves = (
                                (direction == "LONG" and new_sl_f > old_sl) or
                                (direction == "SHORT" and new_sl_f < old_sl)
                            )
                            if sl_improves:
                                sl_f = new_sl_f
                                signal["sl"] = new_sl_f
                                signal["sl_plus_count"] = signal.get("sl_plus_count", 0) + 1
                                signal["sl_plus_history"] = signal.get("sl_plus_history", [])
                                signal["sl_plus_history"].append({
                                    "from": old_sl,
                                    "to": new_sl_f,
                                    "price": price,
                                    "at": int(time.time() * 1000),
                                })
                                db_save_signal(signal)
                                self._emit("signal_sl_updated", {
                                    "id": sig_id,
                                    "symbol": symbol,
                                    "direction": direction,
                                    "old_sl": old_sl,
                                    "new_sl": new_sl_f,
                                    "price": price,
                                    "reason": ai_result.get("reason"),
                                    "timestamp": int(time.time() * 1000),
                                })
                                print(
                                    f" 🛡️ {sig_id} SL+ | {direction} "
                                    f"SL moved {old_sl} → {new_sl_f} "
                                    f"(price={price}) | {ai_result.get('reason')}"
                                )
                            else:
                                print(
                                    f" ⚠️ {sig_id} SL+ rejected — "
                                    f"new_sl={new_sl_f} doesn't improve current sl={old_sl} "
                                    f"for {direction}"
                                )
                        else:
                            print(f" ⚠️ {sig_id} SL+ had no valid new_sl — ignoring")

                    elif ai_result.get("decision") == "CLOSE":
                        pnl_pct = round(
                            (price - entry) / entry * 100 if direction == "LONG"
                            else (entry - price) / entry * 100, 4
                        ) if entry > 0 else 0.0

                        ve_label = "TP" if pnl_pct >= 0 else "SL"
                        pnl_usdt = virtual_exchange.apply_result(
                            ve_label, direction, entry, price, self.user_id
                        )

                        signal.update({
                            "status": "CLOSED",
                            "result": "AI_CLOSE",
                            "pnl_pct": pnl_pct,
                            "pnl_usdt": pnl_usdt,
                            "closed_at": int(time.time() * 1000),
                            "closed_price": price,
                            "close_reason": ai_result.get("reason", "AI decided to close"),
                        })
                        self.state["trade_count"] += 1
                        if pnl_pct >= 0:
                            self.state["win_count"] += 1
                        else:
                            self.state["loss_count"] += 1
                        self.state["total_pnl_pct"] = round(
                            self.state["total_pnl_pct"] + pnl_pct, 4)
                        self.state["total_pnl_usdt"] = round(
                            self.state["total_pnl_usdt"] + pnl_usdt, 4)

                        db_save_signal(signal)
                        self.state["signals"] = [
                            s for s in self.state["signals"] if s["id"] != sig_id
                        ]
                        self.state["active_signal_count"] = self._active_count()
                        self._emit("signal_closed", {
                            **signal,
                            "balance": virtual_exchange.get_info(self.user_id)["balance"],
                        })
                        self._emit("balance_update", virtual_exchange.get_info(self.user_id))
                        print(
                            f" 🤖 {sig_id} AI_CLOSE @ {price} | "
                            f"pnl={pnl_pct}% / {pnl_usdt:+.4f} USDT | "
                            f"reason: {ai_result.get('reason')} | "
                            f"balance={virtual_exchange.get_info(self.user_id)['balance']} USDT | "
                            f"active {self._active_count()}/{MAX_ACTIVE_SIGNALS}"
                        )
                        price_feed.unwatch(symbol)
                        break

                    else:
                        print(
                            f" 🤖 {sig_id} AI says HOLD "
                            f"({ai_result.get('reason', 'no reason given')})"
                        )

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(
                        f" {sig_id} AI position check exception: {e}", exc_info=True
                    )

        if self.running:
            signal = self._find_signal(sig_id)
            if signal and signal.get("status") == "OPEN":
                print(
                    f" ⏰ {sig_id} timed out (8h) — "
                    f"marking INVALIDATED (was: entry_hit={entry_hit})"
                )
                signal.update({
                    "status": "INVALIDATED",
                    "result": "TIMEOUT",
                    "closed_at": int(time.time() * 1000),
                    "closed_price": signal.get("current_price", 0),
                    "pnl_usdt": 0.0,
                    "pnl_pct": 0.0,
                })
                db_save_signal(signal)
                self.state["signals"] = [
                    s for s in self.state["signals"] if s["id"] != sig_id
                ]
                self.state["active_signal_count"] = self._active_count()
                self._emit("signal_invalidated", {
                    "id": sig_id,
                    "symbol": signal.get("symbol"),
                    "price": signal.get("current_price"),
                    "timestamp": int(time.time() * 1000),
                    "reason": "timeout_8h",
                })
                price_feed.unwatch(symbol)

    def _find_signal(self, sig_id: str) -> Optional[Dict]:
        for s in self.state["signals"]:
            if s["id"] == sig_id:
                return s
        return None

    def get_state(self) -> dict:
        wins = self.state["win_count"]
        losses = self.state["loss_count"]
        closed = wins + losses
        winrate = round(wins / closed * 100, 2) if closed > 0 else 0.0
        active = self._active_count()
        balance_info = virtual_exchange.get_info(self.user_id)
        return {
            **self.state,
            "winrate": winrate,
            "active_signal_count": active,
            "max_active_signals": MAX_ACTIVE_SIGNALS,
            "balance": balance_info["balance"],
            "leverage": balance_info["leverage"],
            "entry_usdt": balance_info["entry_usdt"],
        }

    def reset_stats(self):
        self.state.update({
            "signals": [],
            "trade_count": 0,
            "win_count": 0,
            "loss_count": 0,
            "no_trade_count": 0,
            "total_pnl_pct": 0.0,
            "total_pnl_usdt": 0.0,
            "last_signal": None,
            "last_error": None,
            "symbols_scanned": 0,
            "active_signal_count": 0,
        })
        self._pass_scanned = set()
        virtual_exchange.reset(self.user_id)
        if self.user_id:
            db_delete_signals_by_user(self.user_id)
            print(f"🗑️ Signals cleared for user {self.user_id}")


# Singleton global engine (backward compat)
bot_engine = BotEngine(user_id=None)
