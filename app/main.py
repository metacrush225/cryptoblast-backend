"""
Crypto Dashboard API — point d'entrée.
Ce fichier n'a qu'une responsabilité : assembler l'application (lifespan, CORS, routers).
Toute la logique vit dans clients/, services/ et routers/.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import CORS_ORIGINS, DISCORD_ENABLED, RSI_CHECK_INTERVAL_SECONDS, HTTP_TIMEOUT_SECONDS
from app.services.alerts import rsi_background_loop
from app.routers import info, crypto, alerts

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


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

app.include_router(info.router)
app.include_router(crypto.router)
app.include_router(alerts.router)


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
