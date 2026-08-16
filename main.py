"""
Crypto Dashboard API — version améliorée
- Cache TTL pour limiter les appels à Binance (anti rate-limit)
- Retry avec backoff exponentiel sur les erreurs réseau
- Configuration via variables d'environnement (.env)
- Alertes Discord natives en Python (webhook), sans dépendance Node/axios
- Tâche planifiée en arrière-plan pour vérifier le RSI périodiquement
"""

import os
import time
import logging
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, List, Dict, Tuple, Literal

import httpx
import pandas as pd
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from dotenv import load_dotenv

load_dotenv()

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BINANCE_BASE_URL = "https://api.binance.com/api/v3"

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:4200,http://127.0.0.1:4200").split(",")

CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "20"))
HTTP_TIMEOUT_SECONDS = float(os.getenv("HTTP_TIMEOUT_SECONDS", "10"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_BACKOFF_BASE = float(os.getenv("RETRY_BACKOFF_BASE", "0.5"))  # secondes

RSI_CHECK_INTERVAL_SECONDS = int(os.getenv("RSI_CHECK_INTERVAL_SECONDS", "1800"))  # 30 min
RSI_OVERSOLD = float(os.getenv("RSI_OVERSOLD", "30"))
RSI_OVERBOUGHT = float(os.getenv("RSI_OVERBOUGHT", "70"))

# --- Symboles suivis, pilotés par .env (fallback sur une liste par défaut) ---
_default_symbols = "BTCUSDT,ETHUSDT,ADAUSDT,DOTUSDT,LINKUSDT,BNBUSDT,XRPUSDT,SOLUSDT"
VALID_SYMBOLS = [s.strip().upper() for s in os.getenv("SYMBOLS", _default_symbols).split(",") if s.strip()]

# --- Nom lisible par symbole : SYMBOL=Nom lisible dans le .env (ex: XRPUSDT=Ripple) ---
SYMBOL_NAMES = {sym: os.getenv(sym, sym) for sym in VALID_SYMBOLS}

# --- Discord bot (API REST, un seul salon pour toutes les alertes) ---
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_ALERT_CHANNEL_ID = os.getenv("DISCORD_ALERT_CHANNEL_ID")
DISCORD_API_BASE = "https://discord.com/api/v10"

DISCORD_ENABLED = bool(DISCORD_BOT_TOKEN) and bool(DISCORD_ALERT_CHANNEL_ID)

IntervalStr = Literal[
    "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"
]

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


# --------------------------------------------------------------------------
# Modèles Pydantic
# --------------------------------------------------------------------------

class CryptoData(BaseModel):
    symbol: str
    open: float
    close: float
    rsi: float
    timestamp: str
    price_change_24h: float
    volume_24h: float
    sma10: Optional[float] = None
    sma30: Optional[float] = None


class HistoryPoint(BaseModel):
    timestamp: str
    open: float
    close: float
    sma10: Optional[float] = None
    sma30: Optional[float] = None


class HistoryResponse(BaseModel):
    success: bool
    data: List[HistoryPoint] = []
    count: int = 0
    message: Optional[str] = None


class ApiResponse(BaseModel):
    success: bool
    data: Optional[CryptoData] = None
    message: Optional[str] = None


# --------------------------------------------------------------------------
# Cache TTL simple (en mémoire)
# --------------------------------------------------------------------------

class TTLCache:
    """Cache mémoire minimal avec expiration, pour éviter de spammer Binance."""

    def __init__(self, ttl_seconds: int):
        self.ttl = ttl_seconds
        self._store: Dict[str, Tuple[float, object]] = {}

    def get(self, key: str):
        entry = self._store.get(key)
        if not entry:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: object):
        self._store[key] = (time.monotonic() + self.ttl, value)


cache = TTLCache(CACHE_TTL_SECONDS)


# --------------------------------------------------------------------------
# Client Binance : retry + backoff + cache
# --------------------------------------------------------------------------

class BinanceClient:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def _get_with_retry(self, path: str, params: dict) -> dict:
        last_exc = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await self.client.get(f"{BINANCE_BASE_URL}{path}", params=params)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPStatusError, httpx.TransportError) as e:
                last_exc = e
                # Ne pas retry sur les erreurs client (4xx), seulement réseau/5xx
                if isinstance(e, httpx.HTTPStatusError) and e.response.status_code < 500:
                    logger.warning(f"Erreur client Binance ({path}): {e}")
                    raise
                wait = RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                logger.warning(f"Tentative {attempt}/{MAX_RETRIES} échouée pour {path}: {e}. Retry dans {wait:.1f}s")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(wait)
        logger.error(f"Echec définitif après {MAX_RETRIES} tentatives pour {path}: {last_exc}")
        raise last_exc

    async def get_24h_ticker(self, symbol: str) -> dict:
        cache_key = f"ticker:{symbol}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        data = await self._get_with_retry("/ticker/24hr", {"symbol": symbol})
        cache.set(cache_key, data)
        return data

    async def get_klines(self, symbol: str, interval: str, limit: int) -> list:
        cache_key = f"klines:{symbol}:{interval}:{limit}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        data = await self._get_with_retry(
            "/klines", {"symbol": symbol, "interval": interval, "limit": limit}
        )
        cache.set(cache_key, data)
        return data


# --------------------------------------------------------------------------
# Calculs (RSI, SMA)
# --------------------------------------------------------------------------

def calculate_rsi(prices: list, period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    df = pd.DataFrame({"price": prices})
    delta = df["price"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0


def rolling_sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


async def build_crypto_data(binance: BinanceClient, symbol: str) -> CryptoData:
    ticker_data = await binance.get_24h_ticker(symbol)
    klines = await binance.get_klines(symbol, "1h", 50)

    closing_prices = [float(k[4]) for k in klines]
    rsi = calculate_rsi(closing_prices)

    s = pd.Series(closing_prices, dtype=float)
    sma10_series = s.rolling(10).mean()
    sma30_series = s.rolling(30).mean()
    sma10 = float(sma10_series.iloc[-1]) if len(s) >= 10 and not pd.isna(sma10_series.iloc[-1]) else None
    sma30 = float(sma30_series.iloc[-1]) if len(s) >= 30 and not pd.isna(sma30_series.iloc[-1]) else None

    return CryptoData(
        symbol=symbol,
        open=float(ticker_data["openPrice"]),
        close=float(ticker_data["lastPrice"]),
        rsi=round(rsi, 2),
        timestamp=datetime.now().isoformat(),
        price_change_24h=float(ticker_data["priceChangePercent"]),
        volume_24h=float(ticker_data["volume"]),
        sma10=sma10,
        sma30=sma30,
    )


# --------------------------------------------------------------------------
# Alertes Discord (natif Python, pas de Node/axios)
# --------------------------------------------------------------------------

async def send_discord_alert(client: httpx.AsyncClient, content: str):
    """Envoie un message dans le salon d'alertes via l'API bot Discord (pas de webhook)."""
    if not DISCORD_ENABLED:
        logger.debug("Bot Discord non configuré (DISCORD_BOT_TOKEN / DISCORD_ALERT_CHANNEL_ID manquant), alerte ignorée.")
        return
    try:
        response = await client.post(
            f"{DISCORD_API_BASE}/channels/{DISCORD_ALERT_CHANNEL_ID}/messages",
            headers={"Authorization": f"Bot {DISCORD_BOT_TOKEN}"},
            json={"content": content},
        )
        response.raise_for_status()
        logger.info("Alerte Discord envoyée avec succès.")
    except httpx.HTTPError as e:
        logger.error(f"Echec de l'envoi de l'alerte Discord: {e}")


async def check_rsi_and_alert(client: httpx.AsyncClient):
    """Vérifie le RSI de tous les symboles suivis et envoie une alerte Discord si seuil dépassé."""
    binance = BinanceClient(client)
    oversold, overbought = [], []

    for symbol in VALID_SYMBOLS:
        try:
            data = await build_crypto_data(binance, symbol)
            if data.rsi <= RSI_OVERSOLD:
                oversold.append(data)
            elif data.rsi >= RSI_OVERBOUGHT:
                overbought.append(data)
        except Exception as e:
            logger.error(f"Erreur lors du check RSI pour {symbol}: {e}")

    if not oversold and not overbought:
        logger.info("Aucun symbole en zone de survente/surachat.")
        return

    lines = ["📊 **Alerte RSI**"]
    for d in oversold:
        lines.append(f"🟢 SURVENTE — {SYMBOL_NAMES.get(d.symbol, d.symbol)} ({d.symbol}) : RSI {d.rsi} (close {d.close})")
    for d in overbought:
        lines.append(f"🔴 SURACHAT — {SYMBOL_NAMES.get(d.symbol, d.symbol)} ({d.symbol}) : RSI {d.rsi} (close {d.close})")

    await send_discord_alert(client, "\n".join(lines))


async def rsi_background_loop(client: httpx.AsyncClient):
    """Boucle planifiée : vérifie le RSI toutes les RSI_CHECK_INTERVAL_SECONDS."""
    while True:
        try:
            await check_rsi_and_alert(client)
        except Exception as e:
            logger.error(f"Erreur dans la boucle de vérification RSI: {e}")
        await asyncio.sleep(RSI_CHECK_INTERVAL_SECONDS)


# --------------------------------------------------------------------------
# Cycle de vie de l'application
# --------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Démarrage de l'API Crypto Dashboard")
    app.state.http_client = httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS)

    background_task = None
    if DISCORD_ENABLED:
        background_task = asyncio.create_task(rsi_background_loop(app.state.http_client))
        logger.info(f"🔔 Alertes Discord activées (check toutes les {RSI_CHECK_INTERVAL_SECONDS}s)")
    else:
        logger.info("🔕 DISCORD_BOT_TOKEN / DISCORD_ALERT_CHANNEL_ID non définis : alertes Discord désactivées")

    yield

    if background_task:
        background_task.cancel()
    await app.state.http_client.aclose()
    logger.info("🛑 Arrêt de l'API Crypto Dashboard")


# --------------------------------------------------------------------------
# Application FastAPI
# --------------------------------------------------------------------------

app = FastAPI(
    title="Crypto Dashboard API",
    description="API pour récupérer les données crypto avec RSI, Open, Close de Binance",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


def get_binance_client(request: Request) -> BinanceClient:
    return BinanceClient(request.app.state.http_client)


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@app.get("/", tags=["Info"])
async def root():
    return {
        "message": "Crypto Dashboard API",
        "version": "2.0.0",
        "status": "active",
        "endpoints": {
            "crypto_data": "/api/crypto/{symbol}",
            "crypto_history": "/api/crypto/{symbol}/history",
            "health": "/health",
            "docs": "/docs",
        },
    }


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "discord_alerts": DISCORD_ENABLED,
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
    }


@app.get("/api/crypto/{symbol}", response_model=ApiResponse, tags=["Crypto"])
async def get_crypto_data_route(symbol: str, request: Request):
    """Récupère les données crypto (open, close, RSI, SMA, volume) pour un symbole donné."""
    symbol = symbol.upper()

    if symbol not in VALID_SYMBOLS:
        return ApiResponse(
            success=False,
            message=f"Symbole non supporté. Symboles valides: {', '.join(VALID_SYMBOLS)}",
        )

    try:
        binance = get_binance_client(request)
        crypto_data = await build_crypto_data(binance, symbol)
        return ApiResponse(success=True, data=crypto_data, message="Données récupérées avec succès")
    except httpx.HTTPError as e:
        logger.error(f"Erreur Binance pour {symbol}: {e}")
        return ApiResponse(success=False, message="Erreur de connexion à Binance API")
    except Exception as e:
        logger.exception(f"Erreur inattendue pour {symbol}: {e}")
        return ApiResponse(success=False, message="Erreur interne du serveur")


@app.get("/api/crypto/{symbol}/history", response_model=HistoryResponse, tags=["Crypto"])
async def get_crypto_history_route(
    symbol: str, request: Request, interval: IntervalStr = "1h", days: int = 14
):
    """Récupère l'historique crypto (par défaut 14 jours)."""
    symbol = symbol.upper()

    if symbol not in VALID_SYMBOLS:
        return HistoryResponse(
            success=False, data=[], count=0,
            message=f"Symbole non supporté. Symboles valides: {', '.join(VALID_SYMBOLS)}",
        )

    try:
        binance = get_binance_client(request)
        params = INTERVALS_CONFIG.get(interval, {"limit": 336, "actual_days": "14 jours"})
        limit = params["limit"]

        if days != 14:
            hours_needed = days * 24
            limit = min(int(hours_needed / HOURS_PER_POINT.get(interval, 1)), 1000)

        logger.info(f"Récupération de {limit} points pour {symbol} avec intervalle {interval}")

        klines = await binance.get_klines(symbol, interval, limit)

        opens = [float(k[1]) for k in klines]
        closes = [float(k[4]) for k in klines]
        times = [datetime.fromtimestamp(k[0] / 1000).isoformat() for k in klines]

        s_close = pd.Series(closes, dtype=float)
        sma10_s = rolling_sma(s_close, 10)
        sma30_s = rolling_sma(s_close, 30)

        points = [
            HistoryPoint(
                timestamp=times[i],
                open=opens[i],
                close=closes[i],
                sma10=None if pd.isna(sma10_s.iloc[i]) else round(float(sma10_s.iloc[i]), 2),
                sma30=None if pd.isna(sma30_s.iloc[i]) else round(float(sma30_s.iloc[i]), 2),
            )
            for i in range(len(klines))
        ]

        return HistoryResponse(
            success=True, data=points, count=len(points),
            message=f"Historique de {len(points)} points récupéré avec succès ({params['actual_days']})",
        )

    except httpx.HTTPError as e:
        logger.error(f"Erreur Binance (historique) pour {symbol}: {e}")
        return HistoryResponse(success=False, data=[], count=0, message="Erreur de connexion à Binance API")
    except Exception as e:
        logger.exception(f"Erreur lors de la récupération de l'historique pour {symbol}: {e}")
        return HistoryResponse(success=False, data=[], count=0, message="Erreur interne du serveur")


@app.get("/api/crypto", tags=["Crypto"])
async def get_supported_symbols():
    symbols = [
        {
            "symbol": sym,
            "name": SYMBOL_NAMES.get(sym, sym),
            "base": sym.replace("USDT", ""),
            "quote": "USDT",
        }
        for sym in VALID_SYMBOLS
    ]
    return {"success": True, "data": symbols, "count": len(symbols)}


@app.get("/api/intervals", tags=["Info"])
async def get_supported_intervals():
    recommended = {"30m", "1h", "2h", "4h", "1d"}
    intervals = {
        k: {"points": v["limit"], "coverage": v["actual_days"], "recommended": k in recommended}
        for k, v in INTERVALS_CONFIG.items()
    }
    return {
        "success": True,
        "data": intervals,
        "note": "Les intervalles recommandés offrent un bon équilibre entre granularité et performance",
    }


@app.post("/api/alerts/test", tags=["Alerts"])
async def test_discord_alert(request: Request):
    """Déclenche manuellement un check RSI + alerte Discord (utile pour tester la config)."""
    if not DISCORD_ENABLED:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "DISCORD_BOT_TOKEN / DISCORD_ALERT_CHANNEL_ID non configurés"},
        )
    await check_rsi_and_alert(request.app.state.http_client)
    return {"success": True, "message": "Vérification RSI déclenchée, alerte envoyée si seuils dépassés"}


# --------------------------------------------------------------------------
# Gestion des erreurs
# --------------------------------------------------------------------------

@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "message": "Endpoint non trouvé",
                "available_endpoints": [
                    "/api/crypto/{symbol}",
                    "/api/crypto/{symbol}/history",
                    "/api/crypto",
                    "/api/intervals",
                    "/api/alerts/test",
                    "/health",
                    "/docs",
                ],
            },
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})