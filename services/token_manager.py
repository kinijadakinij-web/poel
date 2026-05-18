"""
Token Manager — simpan & update Qwen tokens di memory + database.
Tokens bisa di-update via API tanpa redeploy Railway.
"""

import os
from typing import List, Optional
from services.database import get_setting, set_setting

# Default dari env (fallback kalau DB kosong)
DEFAULT_TOKENS = [
    os.getenv(f"QWEN_TOKEN_{i}", "").strip()
    for i in range(1, 6)
]

class TokenManager:
    def __init__(self):
        self._tokens: List[str] = []
        self._load()

    def _load(self):
        """Load tokens dari DB, fallback ke env."""
        db_tokens = []
        for i in range(1, 6):
            val = get_setting(f"QWEN_TOKEN_{i}")
            if val:
                db_tokens.append(val)
        
        # Kalau DB kosong, pakai env
        if not db_tokens:
            db_tokens = [t for t in DEFAULT_TOKENS if t]
            # Simpan ke DB untuk pertama kali
            for i, t in enumerate(db_tokens, 1):
                set_setting(f"QWEN_TOKEN_{i}", t)
        
        self._tokens = db_tokens

    def get_tokens(self) -> List[str]:
        return self._tokens.copy()

    def update_tokens(self, tokens: List[str]):
        """Update tokens di memory & DB."""
        self._tokens = [t.strip() for t in tokens if t.strip()]
        # Simpan ke DB
        for i in range(1, 6):
            key = f"QWEN_TOKEN_{i}"
            if i <= len(self._tokens):
                set_setting(key, self._tokens[i - 1])
            else:
                set_setting(key, "")
        return self._tokens

    def get_token(self, index: int) -> Optional[str]:
        if 0 <= index < len(self._tokens):
            return self._tokens[index]
        return None

    def token_count(self) -> int:
        return len(self._tokens)


token_manager = TokenManager()
