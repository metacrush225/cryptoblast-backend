"""Dépendances FastAPI partagées entre routers."""

from fastapi import Request

from app.clients.binance import BinanceClient


def get_binance_client(request: Request) -> BinanceClient:
    """Réutilise le httpx.AsyncClient unique créé au démarrage de l'app (voir main.py)."""
    return BinanceClient(request.app.state.http_client)
