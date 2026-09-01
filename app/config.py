"""Configuration centralisée : tout ce qui vient du .env vit ici, et nulle part ailleurs."""

import os
from typing import Literal
from dotenv import load_dotenv

load_dotenv()

# --- Binance ---
BINANCE_BASE_URL = "https://api.binance.com/api/v3"

# --- CORS ---
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:4200,http://127.0.0.1:4200").split(",")

# --- Cache & réseau ---
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "20"))
HTTP_TIMEOUT_SECONDS = float(os.getenv("HTTP_TIMEOUT_SECONDS", "10"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_BACKOFF_BASE = float(os.getenv("RETRY_BACKOFF_BASE", "0.5"))

# --- RSI / alertes ---
RSI_CHECK_INTERVAL_SECONDS = int(os.getenv("RSI_CHECK_INTERVAL_SECONDS", "1800"))
RSI_OVERSOLD = float(os.getenv("RSI_OVERSOLD", "30"))
RSI_OVERBOUGHT = float(os.getenv("RSI_OVERBOUGHT", "70"))

# --- Symboles suivis ---
_default_symbols = "BTCUSDT,ETHUSDT,ADAUSDT,DOTUSDT,LINKUSDT,BNBUSDT,XRPUSDT,SOLUSDT"
VALID_SYMBOLS = [s.strip().upper() for s in os.getenv("SYMBOLS", _default_symbols).split(",") if s.strip()]
SYMBOL_NAMES = {sym: os.getenv(sym, sym) for sym in VALID_SYMBOLS}

# --- Discord bot ---
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_ALERT_CHANNEL_ID = os.getenv("DISCORD_ALERT_CHANNEL_ID")
ALERTS_SCHEDULER_TOKEN = os.getenv("ALERTS_SCHEDULER_TOKEN")
DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_ENABLED = bool(DISCORD_BOT_TOKEN) and bool(DISCORD_ALERT_CHANNEL_ID)

# --- Gemini / IA ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_ENABLED = bool(GEMINI_API_KEY)

# --- Intervalles Binance supportés ---
IntervalStr = Literal["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"]

INTERVALS_CONFIG = {
    "1m": {"limit": 1000, "actual_days": "~16.7 heures"},
    "3m": {"limit": 1000, "actual_days": "~2.1 jours"},
    "5m": {"limit": 1000, "actual_days": "~3.5 jours"},
    "15m": {"limit": 1000, "actual_days": "~10.4 jours"},
    "30m": {"limit": 672, "actual_days": "14 jours"},
    "1h": {"limit": 336, "actual_days": "14 jours"},
    "2h": {"limit": 168, "actual_days": "14 jours"},
    "4h": {"limit": 84, "actual_days": "14 jours"},
    "6h": {"limit": 56, "actual_days": "14 jours"},
    "8h": {"limit": 42, "actual_days": "14 jours"},
    "12h": {"limit": 28, "actual_days": "14 jours"},
    "1d": {"limit": 14, "actual_days": "14 jours"},
}

HOURS_PER_POINT = {
    "1m": 1 / 60, "3m": 3 / 60, "5m": 5 / 60, "15m": 15 / 60, "30m": 0.5,
    "1h": 1, "2h": 2, "4h": 4, "6h": 6, "8h": 8, "12h": 12, "1d": 24,
}
