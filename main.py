from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pydantic import BaseModel
from typing import Optional, List
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

# Fonction utilitaire pour calculer la SMA avec gestion des NaN
def rolling_sma(series: pd.Series, window: int) -> pd.Series:
    """Calcule la moyenne mobile simple avec gestion des NaN"""
    return series.rolling(window=window, min_periods=window).mean()

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

    def get_14days_params(self, interval: str) -> dict:
        """
        Retourne les paramètres optimaux pour récupérer 14 jours d'historique
        selon l'intervalle choisi
        """
        intervals_config = {
            "1m": {"limit": 1000, "actual_days": "~16.7 heures"},  # Max Binance
            "3m": {"limit": 1000, "actual_days": "~2.1 jours"},
            "5m": {"limit": 1000, "actual_days": "~3.5 jours"}, 
            "15m": {"limit": 1000, "actual_days": "~10.4 jours"},
            "30m": {"limit": 672, "actual_days": "14 jours"},     # 30min * 672 = 14j
            "1h": {"limit": 336, "actual_days": "14 jours"},      # 1h * 336 = 14j
            "2h": {"limit": 168, "actual_days": "14 jours"},      # 2h * 168 = 14j
            "4h": {"limit": 84, "actual_days": "14 jours"},       # 4h * 84 = 14j
            "6h": {"limit": 56, "actual_days": "14 jours"},       # 6h * 56 = 14j
            "8h": {"limit": 42, "actual_days": "14 jours"},       # 8h * 42 = 14j
            "12h": {"limit": 28, "actual_days": "14 jours"},      # 12h * 28 = 14j
            "1d": {"limit": 14, "actual_days": "14 jours"},       # 1d * 14 = 14j
        }
        
        return intervals_config.get(interval, {"limit": 336, "actual_days": "14 jours"})

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
            
            s = pd.Series(closing_prices, dtype=float)
            sma10 = float(s.rolling(10).mean().iloc[-1]) if len(s) >= 10 and not pd.isna(s.rolling(10).mean().iloc[-1]) else None
            sma30 = float(s.rolling(30).mean().iloc[-1]) if len(s) >= 30 and not pd.isna(s.rolling(30).mean().iloc[-1]) else None

            # Construction de l'objet de réponse
            crypto_data = CryptoData(
                symbol=symbol,
                open=float(ticker_data['openPrice']),
                close=float(ticker_data['lastPrice']),
                rsi=round(rsi, 2),
                timestamp=datetime.now().isoformat(),
                price_change_24h=float(ticker_data['priceChangePercent']),
                volume_24h=float(ticker_data['volume']),
                sma10=sma10,
                sma30=sma30
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
            "crypto_history": "/api/crypto/{symbol}/history",
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

@app.get("/api/crypto/{symbol}/history", response_model=HistoryResponse, tags=["Crypto"])
async def get_crypto_history(symbol: str, interval: str = "1h", days: int = 14):
    """
    Récupère l'historique crypto sur 14 jours (par défaut)
    
    - **symbol**: Symbole de la crypto (ex: BTCUSDT, ETHUSDT)
    - **interval**: Intervalle temporel (1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d)
    - **days**: Nombre de jours d'historique (par défaut: 14)
    
    Intervalles recommandés pour 14 jours:
    - 1h : 336 points (recommandé)
    - 2h : 168 points  
    - 4h : 84 points
    - 1d : 14 points
    """
    symbol = symbol.upper()
    valid_symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "DOTUSDT", "LINKUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT"]
    
    if symbol not in valid_symbols:
        return HistoryResponse(
            success=False, 
            data=[], 
            count=0,
            message=f"Symbole non supporté. Symboles valides: {', '.join(valid_symbols)}"
        )

    try:
        async with CryptoDataManager() as manager:
            # Calcul du nombre de points nécessaires selon l'intervalle
            params = manager.get_14days_params(interval)
            limit = params["limit"]
            
            # Ajustement si l'utilisateur veut plus ou moins de 14 jours
            if days != 14:
                # Calcul approximatif basé sur l'intervalle
                hours_per_point = {
                    "1m": 1/60, "3m": 3/60, "5m": 5/60, "15m": 15/60, "30m": 0.5,
                    "1h": 1, "2h": 2, "4h": 4, "6h": 6, "8h": 8, "12h": 12, "1d": 24
                }
                hours_needed = days * 24
                limit = min(int(hours_needed / hours_per_point.get(interval, 1)), 1000)  # Max 1000 (limite Binance)
            
            logger.info(f"Récupération de {limit} points pour {symbol} avec intervalle {interval}")
            
            klines = await manager.get_klines(symbol, interval=interval, limit=limit)
            
            # Traitement des données
            opens = [float(k[1]) for k in klines]
            closes = [float(k[4]) for k in klines]
            times = [datetime.fromtimestamp(k[0] / 1000).isoformat() for k in klines]

            # Calcul des moyennes mobiles
            s_close = pd.Series(closes, dtype=float)
            sma10_s = rolling_sma(s_close, 10)
            sma30_s = rolling_sma(s_close, 30)

            # Construction des points d'historique
            points: List[HistoryPoint] = []
            for i in range(len(klines)):
                p = HistoryPoint(
                    timestamp=times[i],
                    open=opens[i],
                    close=closes[i],
                    sma10=None if pd.isna(sma10_s.iloc[i]) else round(float(sma10_s.iloc[i]), 2),
                    sma30=None if pd.isna(sma30_s.iloc[i]) else round(float(sma30_s.iloc[i]), 2),
                )
                points.append(p)

            return HistoryResponse(
                success=True, 
                data=points, 
                count=len(points),
                message=f"Historique de {len(points)} points récupéré avec succès ({params['actual_days']})"
            )

    except Exception as e:
        logger.exception(f"Erreur lors de la récupération de l'historique pour {symbol}: {e}")
        return HistoryResponse(
            success=False, 
            data=[], 
            count=0, 
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

@app.get("/api/intervals", tags=["Info"])
async def get_supported_intervals():
    """
    Retourne les intervalles supportés et leurs configurations pour 14 jours
    """
    intervals = {
        "1m": {"points": 1000, "coverage": "~16.7 heures", "recommended": False},
        "3m": {"points": 1000, "coverage": "~2.1 jours", "recommended": False},
        "5m": {"points": 1000, "coverage": "~3.5 jours", "recommended": False},
        "15m": {"points": 1000, "coverage": "~10.4 jours", "recommended": False},
        "30m": {"points": 672, "coverage": "14 jours", "recommended": True},
        "1h": {"points": 336, "coverage": "14 jours", "recommended": True},
        "2h": {"points": 168, "coverage": "14 jours", "recommended": True},
        "4h": {"points": 84, "coverage": "14 jours", "recommended": True},
        "6h": {"points": 56, "coverage": "14 jours", "recommended": False},
        "8h": {"points": 42, "coverage": "14 jours", "recommended": False},
        "12h": {"points": 28, "coverage": "14 jours", "recommended": False},
        "1d": {"points": 14, "coverage": "14 jours", "recommended": True},
    }
    
    return {
        "success": True,
        "data": intervals,
        "note": "Les intervalles recommandés offrent un bon équilibre entre granularité et performance"
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
                    "/api/crypto/{symbol}/history",
                    "/api/crypto",
                    "/api/intervals",
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