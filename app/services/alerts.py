"""Orchestration : vérifie le RSI de tous les symboles et déclenche les alertes Discord."""

import asyncio
import logging

import httpx

from app.config import VALID_SYMBOLS, RSI_OVERSOLD, RSI_OVERBOUGHT, RSI_CHECK_INTERVAL_SECONDS
from app.clients.binance import BinanceClient
from app.clients.discord import send_discord_alert_with_chart
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

            await send_discord_alert_with_chart(
                client,
                symbol,
                data.rsi,
                data.close,
                oversold=is_oversold,
                chart_png=chart_png,
            )
            alerts_sent += 1

        except Exception as e:
            logger.error(f"Erreur lors du check RSI pour {symbol}: {e}")

    if alerts_sent == 0:
        logger.info("Aucun symbole en zone de survente/surachat.")


async def rsi_background_loop(client: httpx.AsyncClient):
    """Boucle planifiée : vérifie le RSI toutes les RSI_CHECK_INTERVAL_SECONDS."""
    while True:
        try:
            await check_rsi_and_alert(client)
        except Exception as e:
            logger.error(f"Erreur dans la boucle de vérification RSI: {e}")
        await asyncio.sleep(RSI_CHECK_INTERVAL_SECONDS)
