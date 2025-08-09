from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pydantic import BaseModel
from typing import Optional
import httpx
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import asyncio
import logging
from contextlib import asynccontextmanager
from starlette.exceptions import HTTPException as StarletteHTTPException

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Modèles Pydantic
class CryptoData(BaseModel):
    symbol: str
    open: float
    close: float
    rsi: float
    timestamp: str
    price_change_24h: float
    volume_24h: float

class ApiResponse(BaseModel):
    success: bool
    data: Optional[CryptoData] = None
    message: Optional[str] = None

# Classe pour gérer les données crypto
class CryptoDataManager:
    def __init__(self):
        self.base_url = "https://api.binance.com/api/v3"
        self.client = None
        
    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=10.0)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    def calculate_rsi(self, prices: list, period: int = 14) -> float:
        """
        Calcule le RSI (Relative Strength Index)
        """
        if len(prices) < period + 1:
            return 50.0  # Valeur par défaut si pas assez de données
        
        df = pd.DataFrame({'price': prices})
        delta = df['price'].diff()
        
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0

    async def get_24h_ticker(self, symbol: str) -> dict:
        """
        Récupère les données 24h ticker de Binance
        """
        try:
            response = await self.client.get(f"{self.base_url}/ticker/24hr", params={"symbol": symbol})
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Erreur lors de la récupération du ticker 24h: {e}")
            raise HTTPException(status_code=500, detail="Erreur de connexion à Binance API")

    async def get_klines(self, symbol: str, interval: str = "1h", limit: int = 50) -> list:
        """
        Récupère les données de chandeliers (klines) de Binance
        """
        try:
            response = await self.client.get(
                f"{self.base_url}/klines",
                params={
                    "symbol": symbol,
                    "interval": interval,
                    "limit": limit
                }
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Erreur lors de la récupération des klines: {e}")
            raise HTTPException(status_code=500, detail="Erreur de connexion à Binance API")

    async def get_crypto_data(self, symbol: str) -> CryptoData:
        """
        Récupère toutes les données crypto nécessaires
        """
        try:
            # Récupération des données 24h
            ticker_data = await self.get_24h_ticker(symbol)
            
            # Récupération des données historiques pour le RSI
            klines = await self.get_klines(symbol, "1h", 50)
            
            # Extraction des prix de clôture pour le calcul du RSI
            closing_prices = [float(kline[4]) for kline in klines]  # Index 4 = close price
            
            # Calcul du RSI
            rsi = self.calculate_rsi(closing_prices)
            
            # Construction de l'objet de réponse
            crypto_data = CryptoData(
                symbol=symbol,
                open=float(ticker_data['openPrice']),
                close=float(ticker_data['lastPrice']),
                rsi=round(rsi, 2),
                timestamp=datetime.now().isoformat(),
                price_change_24h=float(ticker_data['priceChangePercent']),
                volume_24h=float(ticker_data['volume'])
            )
            
            return crypto_data
            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des données pour {symbol}: {e}")
            raise HTTPException(status_code=500, detail=f"Impossible de récupérer les données pour {symbol}")

# Gestionnaire d'événements pour l'application
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Démarrage
    logger.info("🚀 Démarrage de l'API Crypto Dashboard")
    yield
    # Arrêt
    logger.info("🛑 Arrêt de l'API Crypto Dashboard")

# Création de l'application FastAPI
app = FastAPI(
    title="Crypto Dashboard API",
    description="API pour récupérer les données crypto avec RSI, Open, Close de Binance",
    version="1.0.0",
    lifespan=lifespan
)

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://127.0.0.1:4200"],  # Angular dev server
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Routes de l'API
@app.get("/", tags=["Info"])
async def root():
    """
    Point d'entrée de l'API
    """
    return {
        "message": "Crypto Dashboard API",
        "version": "1.0.0",
        "status": "active",
        "endpoints": {
            "crypto_data": "/api/crypto/{symbol}",
            "health": "/health",
            "docs": "/docs"
        }
    }

@app.get("/health", tags=["Health"])
async def health_check():
    """
    Vérification de l'état de l'API
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "uptime": "OK"
    }

@app.get("/api/crypto/{symbol}", response_model=ApiResponse, tags=["Crypto"])
async def get_crypto_data(symbol: str):
    """
    Récupère les données crypto pour un symbole donné
    
    - **symbol**: Symbole de la crypto (ex: BTCUSDT, ETHUSDT)
    
    Retourne les données suivantes:
    - Open: Prix d'ouverture 24h
    - Close: Prix actuel
    - RSI: Relative Strength Index
    - Volume 24h
    - Changement de prix 24h en %
    """
    symbol = symbol.upper()
    
    # Validation du symbole
    valid_symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "DOTUSDT", "LINKUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT"]
    if symbol not in valid_symbols:
        return ApiResponse(
            success=False,
            message=f"Symbole non supporté. Symboles valides: {', '.join(valid_symbols)}"
        )
    
    try:
        async with CryptoDataManager() as manager:
            crypto_data = await manager.get_crypto_data(symbol)
            
            return ApiResponse(
                success=True,
                data=crypto_data,
                message="Données récupérées avec succès"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur inattendue: {e}")
        return ApiResponse(
            success=False,
            message="Erreur interne du serveur"
        )

@app.get("/api/crypto", tags=["Crypto"])
async def get_supported_symbols():
    """
    Retourne la liste des symboles supportés
    """
    symbols = [
        {"symbol": "BTCUSDT", "name": "Bitcoin", "base": "BTC", "quote": "USDT"},
        {"symbol": "ETHUSDT", "name": "Ethereum", "base": "ETH", "quote": "USDT"},
        {"symbol": "ADAUSDT", "name": "Cardano", "base": "ADA", "quote": "USDT"},
        {"symbol": "DOTUSDT", "name": "Polkadot", "base": "DOT", "quote": "USDT"},
        {"symbol": "LINKUSDT", "name": "Chainlink", "base": "LINK", "quote": "USDT"},
        {"symbol": "BNBUSDT", "name": "Binance Coin", "base": "BNB", "quote": "USDT"},
        {"symbol": "XRPUSDT", "name": "XRP", "base": "XRP", "quote": "USDT"},
        {"symbol": "SOLUSDT", "name": "Solana", "base": "SOL", "quote": "USDT"},
    ]
    
    return {
        "success": True,
        "data": symbols,
        "count": len(symbols)
    }

# Gestion des erreurs
@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    # Cas 404
    if exc.status_code == 404:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "message": "Endpoint non trouvé",
                "available_endpoints": [
                    "/api/crypto/{symbol}",
                    "/api/crypto",
                    "/health",
                    "/docs"
                ]
            }
        )
    # Pour les autres HTTPException, on laisse FastAPI gérer le détail
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )