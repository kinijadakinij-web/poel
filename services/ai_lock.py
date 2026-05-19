"""
Shared AI request lock — digunakan oleh position_ai (monitor).

qwen_ai (scanner) TIDAK lagi menggunakan lock global ini.
Setiap QwenAIClient kini punya per-instance lock sendiri,
sehingga 3 token bisa berjalan paralel sekaligus.

position_ai tetap pakai lock ini karena masih single-client.

Usage (position_ai):
    from services.ai_lock import ai_lock

    async with ai_lock():
        resp = await client.post(...)
"""

import asyncio

# Lazy init — asyncio.Lock() harus dibuat di dalam running event loop
_lock: asyncio.Lock | None = None


def ai_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


# Bisa dipakai sebagai context manager langsung:
#   async with ai_lock():  ...
# Atau simpan referensi:
#   lock = ai_lock()
#   async with lock: ...
