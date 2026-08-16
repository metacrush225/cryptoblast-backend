"""Routes d'information générale : racine, health check, intervalles supportés."""

from datetime import datetime

from fastapi import APIRouter

from app.config import DISCORD_ENABLED, CACHE_TTL_SECONDS, INTERVALS_CONFIG

router = APIRouter(tags=["Info"])


@router.get("/")
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


@router.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "discord_alerts": DISCORD_ENABLED,
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
    }


@router.get("/api/intervals")
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
