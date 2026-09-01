"""Orchestration : vérifie le RSI de tous les symboles et déclenche les alertes Discord."""

import logging

import httpx
import pandas as pd

from app.config import VALID_SYMBOLS, RSI_OVERSOLD, RSI_OVERBOUGHT, GEMINI_ENABLED
from app.clients.binance import BinanceClient
from app.clients.discord import send_discord_alert_with_chart
from app.services.ai_analysis import analyze_chart_and_data
from app.services.crypto import build_crypto_data
from app.services.chart import generate_chart_png

logger = logging.getLogger(__name__)


async def check_rsi_and_alert(client: httpx.AsyncClient):
    """Vérifie le RSI de tous les symboles suivis et envoie une alerte (embed + graphique) si seuil dépassé."""
    binance = BinanceClient(client)
    alerts_sent = 0

    for symbol in VALID_SYMBOLS:
        try:
            data = await build_crypto_data(binance, symbol)
            is_oversold = data.rsi <= RSI_OVERSOLD
            is_overbought = data.rsi >= RSI_OVERBOUGHT

            if not is_oversold and not is_overbought:
                continue

            # Historique un peu plus long pour un graphique lisible (ex: 5 derniers jours en 1h)
            klines = await binance.get_klines(symbol, "1h", 120)
            chart_png = generate_chart_png(
                symbol=symbol,
                klines=klines,
                rsi_value=data.rsi,
            )

            ai_summary = None
            if GEMINI_ENABLED:
                try:
                    closes = [float(k[4]) for k in klines]
                    s = pd.Series(closes, dtype=float)
                    recent_df = pd.DataFrame({
                        "close": closes,
                        "rsi": [float(data.rsi)] * len(closes),
                        "sma_10": s.rolling(10).mean(),
                        "sma_30": s.rolling(30).mean(),
                    }).tail(10)
                    ai_summary = await analyze_chart_and_data(
                        image_bytes=chart_png,
                        symbol=symbol,
                        df_last_candles=recent_df,
                    )
                except Exception as exc:
                    logger.warning(f"Analyse IA non disponible pour {symbol}: {exc}")

            await send_discord_alert_with_chart(
                client,
                symbol,
                data.rsi,
                data.close,
                oversold=is_oversold,
                chart_png=chart_png,
                ai_summary=ai_summary,
            )
            alerts_sent += 1

        except Exception as e:
            logger.error(f"Erreur lors du check RSI pour {symbol}: {e}")

    if alerts_sent == 0:
        logger.info("Aucun symbole en zone de survente/surachat.")
