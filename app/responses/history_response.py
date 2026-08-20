"""Schémas Pydantic partagés par les routers."""

from typing import Optional, List
from pydantic import BaseModel

from app.models.history_point import HistoryPoint



class HistoryResponse(BaseModel):
    success: bool
    data: List[HistoryPoint] = []
    count: int = 0
    message: Optional[str] = None

