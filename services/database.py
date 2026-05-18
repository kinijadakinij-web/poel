import sqlite3
import os
import time
import json
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, List, Dict, Any

DB_DIR = Path(os.getenv("DB_DIR", "/app/data"))
DB_PATH = DB_DIR / "agentx.db"

@contextmanager
def get_db():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def _migrate_v2(conn):
    """Add new columns for TP1/TP2/MAX and sl_trigger_price."""
    columns_to_add = [
        ("tp1", "REAL"),
        ("tp2", "REAL"),
        ("tp_max", "REAL"),
        ("sl_trigger_price", "REAL"),
    ]
    existing = conn.execute("PRAGMA table_info(signals)").fetchall()
    existing_cols = {c[1] for c in existing}
    for col, ctype in columns_to_add:
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE signals ADD COLUMN {col} {ctype}")
            print(f"[DB] Migrated: added column {col} {ctype}")

def init_db():
    with get_db() as conn:
        sql = """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            passkey_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            leverage INTEGER DEFAULT 10,
            margin REAL DEFAULT 100,
            balance REAL DEFAULT 1000,
            initial_balance REAL DEFAULT 1000,
            created_at INTEGER
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS signals (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            symbol TEXT,
            timestamp INTEGER,
            current_price REAL,
            trend TEXT,
            pattern TEXT,
            decision TEXT,
            entry REAL,
            tp REAL,
            tp1 REAL,
            tp2 REAL,
            tp_max REAL,
            sl REAL,
            sl_trigger_price REAL,
            invalidation REAL,
            reason TEXT,
            confidence INTEGER,
            status TEXT,
            result TEXT,
            pnl_pct REAL,
            pnl_usdt REAL,
            closed_at INTEGER,
            closed_price REAL,
            entry_hit INTEGER DEFAULT 0,
            sl_plus_count INTEGER DEFAULT 0,
            sl_plus_history TEXT,
            last_ai_decision TEXT,
            last_ai_reason TEXT,
            last_ai_at INTEGER,
            created_at INTEGER
        );

        CREATE INDEX IF NOT EXISTS idx_signals_user ON signals(user_id);
        CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);
        CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol);
        """
        conn.executescript(sql)

        # Migrate existing tables
        _migrate_v2(conn)
        conn.commit()

# ── Users ──
def create_user(user_id: str, username: str, passkey_hash: str, is_admin: int = 0,
                leverage: int = 10, margin: float = 100, balance: float = 1000):
    with get_db() as conn:
        conn.execute("""
        INSERT INTO users (id, username, passkey_hash, is_admin, leverage, margin, balance, initial_balance, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, username.lower(), passkey_hash, is_admin, leverage, margin, balance, balance, int(time.time())))
        conn.commit()

def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        row = conn.execute('SELECT * FROM users WHERE username = ?', (username.lower(),)).fetchone()
        return dict(row) if row else None

def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        row = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        return dict(row) if row else None

def update_user(user_id: str, fields: Dict[str, Any]):
    with get_db() as conn:
        if not fields:
            return
        sets = ', '.join(f"{k} = ?" for k in fields)
        vals = list(fields.values()) + [user_id]
        conn.execute(f'UPDATE users SET {sets} WHERE id = ?', vals)
        conn.commit()

def list_users() -> List[Dict[str, Any]]:
    with get_db() as conn:
        return [dict(r) for r in conn.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()]

# ── Signals ──
def db_save_signal(signal: Dict[str, Any]):
    with get_db() as conn:
        sig = dict(signal)
        for k in ['sl_plus_history']:
            if k in sig and isinstance(sig[k], (list, dict)):
                sig[k] = json.dumps(sig[k])
        cols = list(sig.keys())
        placeholders = ', '.join('?' for _ in cols)
        conn.execute(f"""
        INSERT OR REPLACE INTO signals ({', '.join(cols)})
        VALUES ({placeholders})
        """, list(sig.values()))
        conn.commit()

def db_get_signals(user_id: Optional[str] = None, limit: int = 500,
                   status: Optional[str] = None, result: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_db() as conn:
        query = 'SELECT * FROM signals WHERE 1=1'
        params = []
        if user_id is not None:
            query += ' AND user_id = ?'
            params.append(user_id)
        else:
            query += ' AND user_id IS NULL'
        if status:
            query += ' AND status = ?'
            params.append(status)
        if result:
            query += ' AND result = ?'
            params.append(result)
        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            if d.get('sl_plus_history'):
                try:
                    d['sl_plus_history'] = json.loads(d['sl_plus_history'])
                except:
                    d['sl_plus_history'] = []
            else:
                d['sl_plus_history'] = []
            results.append(d)
        return results

def db_get_signal_by_id(sig_id: str) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        row = conn.execute('SELECT * FROM signals WHERE id = ?', (sig_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get('sl_plus_history'):
            try:
                d['sl_plus_history'] = json.loads(d['sl_plus_history'])
            except:
                d['sl_plus_history'] = []
        else:
            d['sl_plus_history'] = []
        return d

def db_delete_signals_by_user(user_id: str):
    with get_db() as conn:
        conn.execute('DELETE FROM signals WHERE user_id = ?', (user_id,))
        conn.commit()

def db_count_signals(user_id: Optional[str] = None, status: Optional[str] = None, result: Optional[str] = None) -> int:
    with get_db() as conn:
        query = 'SELECT COUNT(*) FROM signals WHERE 1=1'
        params = []
        if user_id is not None:
            query += ' AND user_id = ?'
            params.append(user_id)
        else:
            query += ' AND user_id IS NULL'
        if status:
            query += ' AND status = ?'
            params.append(status)
        if result:
            query += ' AND result = ?'
            params.append(result)
        return conn.execute(query, params).fetchone()[0]
# ── Settings (key-value store) ──
_SETTINGS_DDL = "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"

def _ensure_settings_table(conn):
    """Auto-create settings table. Safe to call before init_db() runs."""
    conn.execute(_SETTINGS_DDL)

def get_setting(key: str) -> Optional[str]:
    """Baca satu setting. Aman dipanggil sebelum init_db() selesai."""
    with get_db() as conn:
        _ensure_settings_table(conn)
        row = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
        return row[0] if row else None

def set_setting(key: str, value: str):
    """Simpan/update satu setting (upsert). Aman dipanggil sebelum init_db() selesai."""
    with get_db() as conn:
        _ensure_settings_table(conn)
        conn.execute(
            'INSERT INTO settings (key, value) VALUES (?, ?)'
            ' ON CONFLICT(key) DO UPDATE SET value = excluded.value',
            (key, value)
        )
        conn.commit()
