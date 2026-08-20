"""Schémas Pydantic partagés par les routers."""

from typing import Optional
from pydantic import BaseModel


class HistoryPoint(BaseModel):
    timestamp: str
    open: float
    close: float
    sma10: Optional[float] = None
    sma30: Optional[float] = None
