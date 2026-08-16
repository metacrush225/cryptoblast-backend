"""Schémas Pydantic partagés par les routers."""

from typing import Optional, List
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


class HistoryPoint(BaseModel):
    timestamp: str
    open: float
    close: float
    sma10: Optional[float] = None
    sma30: Optional[float] = None


class HistoryResponse(BaseModel):
    success: bool
    data: List[HistoryPoint] = []
    count: int = 0
    message: Optional[str] = None


class ApiResponse(BaseModel):
    success: bool
    data: Optional[CryptoData] = None
    message: Optional[str] = None
