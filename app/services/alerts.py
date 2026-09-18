"""Orchestration : vérifie le RSI de tous les symboles et déclenche les alertes Discord."""

import logging

import httpx
import pandas as pd

from app.config import VALID_SYMBOLS, RSI_OVERSOLD, RSI_OVERBOUGHT, GEMINI_ENABLED
from app.clients.binance import BinanceClient
from app.clients.discord import send_discord_alert_with_chart
from app.services.ai_analysis import analyze_chart_and_data
from app.services.crypto import (
    build_crypto_data,
    rolling_sma,
    calculate_ema,
    calculate_macd,
    calculate_atr,
)
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
                    highs = pd.Series([float(k[2]) for k in klines], dtype=float)
                    lows = pd.Series([float(k[3]) for k in klines], dtype=float)
                    closes = pd.Series([float(k[4]) for k in klines], dtype=float)
                    volumes = pd.Series([float(k[5]) for k in klines], dtype=float)
                    macd_series, signal_series = calculate_macd(closes)

                    recent_df = pd.DataFrame({
                        "close": closes,
                        "rsi": [float(data.rsi)] * len(closes),
                        "sma_10": rolling_sma(closes, 10),
                        "sma_30": rolling_sma(closes, 30),
                        "volume": volumes,
                        "volume_ma_20": rolling_sma(volumes, 20),
                        "ema_9": calculate_ema(closes, 9),
                        "ema_21": calculate_ema(closes, 21),
                        "macd": macd_series,
                        "signal": signal_series,
                        "atr_14": calculate_atr(highs, lows, closes, 14),
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
