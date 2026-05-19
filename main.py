"""
main.py — FastAPI entry point
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.database import init_db
from services.auth_service import seed_admin
from services.mexc_price_feed import price_feed
from routes.auth_routes import router as auth_router
from routes.bot import router as bot_router
from routes.history import router as history_router
from routes.market import router as market_router
from routes.trading import router as trading_router
from routes.admin_routes import router as admin_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────
    logger.info("🚀 Starting up...")
    init_db()
    logger.info("✅ Database initialized")

    seed_admin()
    logger.info("✅ Admin seeded")

    asyncio.create_task(price_feed.start())
    logger.info("✅ MEXC price feed started")

    yield

    # ── Shutdown ─────────────────────────────────────────────
    logger.info("🛑 Shutting down...")
    await price_feed.stop()


app = FastAPI(
    title="Sonnet Trading Bot",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────
app.include_router(auth_router,   prefix="/api/auth",    tags=["auth"])
app.include_router(bot_router,    prefix="/api/bot",     tags=["bot"])
app.include_router(history_router,prefix="/api/history", tags=["history"])
app.include_router(market_router, prefix="/api/market",  tags=["market"])
app.include_router(trading_router,prefix="/api/trading", tags=["trading"])
app.include_router(admin_router,  prefix="/api/admin",   tags=["admin"])


@app.get("/")
async def root():
    return {"status": "ok", "message": "Sonnet Trading Bot API"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
