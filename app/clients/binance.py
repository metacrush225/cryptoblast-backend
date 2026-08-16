"""Client HTTP pour l'API publique Binance : retry avec backoff + cache TTL."""

import asyncio
import logging

import httpx

from app.config import BINANCE_BASE_URL, MAX_RETRIES, RETRY_BACKOFF_BASE
from app.cache import cache

logger = logging.getLogger(__name__)


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
