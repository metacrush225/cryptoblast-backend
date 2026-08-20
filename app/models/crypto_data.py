"""Schémas Pydantic partagés par les routers."""

from typing import Optional
from pydantic import BaseModel

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