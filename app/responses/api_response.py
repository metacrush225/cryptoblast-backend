"""Schémas Pydantic partagés par les routers."""

from typing import Optional, List
from pydantic import BaseModel
from app.models.crypto_data import CryptoData


class ApiResponse(BaseModel):
    success: bool
    data: Optional[CryptoData] = None
    message: Optional[str] = None