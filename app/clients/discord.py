"""Envoi de messages Discord via l'API bot REST (pas de webhook, pas d'axios)."""

import json
import logging
from datetime import datetime

import httpx

from app.config import (
    DISCORD_ENABLED, DISCORD_API_BASE, DISCORD_ALERT_CHANNEL_ID, DISCORD_BOT_TOKEN,
    SYMBOL_NAMES, RSI_OVERSOLD, RSI_OVERBOUGHT,
)

logger = logging.getLogger(__name__)


async def send_discord_alert(client: httpx.AsyncClient, content: str):
    """Envoie un message texte simple dans le salon d'alertes (sans graphique)."""
    if not DISCORD_ENABLED:
        logger.debug("Bot Discord non configuré, alerte ignorée.")
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


async def send_discord_alert_with_chart(
    client: httpx.AsyncClient,
    symbol: str,
    rsi: float,
    close: float,
    oversold: bool,
    chart_png: bytes,
    ai_summary: str | None = None,
):
    """Envoie un embed + graphique en pièce jointe, avec synthèse IA optionnelle."""
    if not DISCORD_ENABLED:
        logger.debug("Bot Discord non configuré, alerte avec graphique ignorée.")
        return

    name = SYMBOL_NAMES.get(symbol, symbol)
    description = (
        f"Le RSI de **{name}** est "
        f"{'< ' + str(RSI_OVERSOLD) + ' (survente)' if oversold else '> ' + str(RSI_OVERBOUGHT) + ' (surachat)'}." 
        f"\nRSI actuel : **{rsi}** — Close : **{close}**"
    )
    if ai_summary:
        description += f"\n\n**Analyse IA**\n{ai_summary}"

    embed = {
        "color": 0xFF0000 if oversold else 0x00FF00,
        "title": f"⚠️ {'Oversold' if oversold else 'Overbought'} : {name}",
        "description": description,
        "image": {"url": f"attachment://{symbol}-chart.png"},
        "timestamp": datetime.now().isoformat(),
        "footer": {"text": "RSI Alert System"},
    }

    files = {
        "files[0]": (f"{symbol}-chart.png", chart_png, "image/png"),
        "payload_json": (None, json.dumps({"embeds": [embed]}), "application/json"),
    }

    try:
        response = await client.post(
            f"{DISCORD_API_BASE}/channels/{DISCORD_ALERT_CHANNEL_ID}/messages",
            headers={"Authorization": f"Bot {DISCORD_BOT_TOKEN}"},
            files=files,
        )
        response.raise_for_status()
        logger.info(f"Alerte Discord avec graphique envoyée pour {symbol}.")
    except httpx.HTTPError as e:
        logger.error(f"Echec de l'envoi de l'alerte avec graphique pour {symbol}: {e}")
