"""Routes crypto : données temps réel, historique, liste des symboles supportés."""

import logging

import httpx
import pandas as pd
from fastapi import APIRouter, Depends

from app.config import VALID_SYMBOLS, SYMBOL_NAMES, INTERVALS_CONFIG, HOURS_PER_POINT, IntervalStr
from app.models.history_point import HistoryPoint
from app.responses.api_response import ApiResponse
from app.responses.history_response import HistoryResponse
from app.clients.binance import BinanceClient
from app.services.crypto import build_crypto_data, rolling_sma
from app.dependencies import get_binance_client
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crypto", tags=["Crypto"])


@router.get("/{symbol}", response_model=ApiResponse)
async def get_crypto_data_route(symbol: str, binance: BinanceClient = Depends(get_binance_client)):
    """Récupère les données crypto (open, close, RSI, SMA, volume) pour un symbole donné."""
    symbol = symbol.upper()

    if symbol not in VALID_SYMBOLS:
        return ApiResponse(
            success=False,
            message=f"Symbole non supporté. Symboles valides: {', '.join(VALID_SYMBOLS)}",
        )

    try:
        crypto_data = await build_crypto_data(binance, symbol)
        return ApiResponse(success=True, data=crypto_data, message="Données récupérées avec succès")
    except httpx.HTTPError as e:
        logger.error(f"Erreur Binance pour {symbol}: {e}")
        return ApiResponse(success=False, message="Erreur de connexion à Binance API")
    except Exception as e:
        logger.exception(f"Erreur inattendue pour {symbol}: {e}")
        return ApiResponse(success=False, message="Erreur interne du serveur")


@router.get("/{symbol}/history", response_model=HistoryResponse)
async def get_crypto_history_route(
    symbol: str,
    interval: IntervalStr = "1h",
    days: int = 14,
    binance: BinanceClient = Depends(get_binance_client),
):
    """Récupère l'historique crypto (par défaut 14 jours)."""
    symbol = symbol.upper()

    if symbol not in VALID_SYMBOLS:
        return HistoryResponse(
            success=False, data=[], count=0,
            message=f"Symbole non supporté. Symboles valides: {', '.join(VALID_SYMBOLS)}",
        )

    try:
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


@router.get("")
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
