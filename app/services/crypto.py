"""Logique métier : indicateurs techniques (RSI, SMA) et agrégation des données crypto."""

from datetime import datetime

import pandas as pd

from app.clients.binance import BinanceClient
from app.models import CryptoData


def calculate_rsi(prices: list, period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    df = pd.DataFrame({"price": prices})
    delta = df["price"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0


def rolling_sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


async def build_crypto_data(binance: BinanceClient, symbol: str) -> CryptoData:
    ticker_data = await binance.get_24h_ticker(symbol)
    klines = await binance.get_klines(symbol, "1h", 50)

    closing_prices = [float(k[4]) for k in klines]
    rsi = calculate_rsi(closing_prices)

    s = pd.Series(closing_prices, dtype=float)
    sma10_series = s.rolling(10).mean()
    sma30_series = s.rolling(30).mean()
    sma10 = float(sma10_series.iloc[-1]) if len(s) >= 10 and not pd.isna(sma10_series.iloc[-1]) else None
    sma30 = float(sma30_series.iloc[-1]) if len(s) >= 30 and not pd.isna(sma30_series.iloc[-1]) else None

    return CryptoData(
        symbol=symbol,
        open=float(ticker_data["openPrice"]),
        close=float(ticker_data["lastPrice"]),
        rsi=round(rsi, 2),
        timestamp=datetime.now().isoformat(),
        price_change_24h=float(ticker_data["priceChangePercent"]),
        volume_24h=float(ticker_data["volume"]),
        sma10=sma10,
        sma30=sma30,
    )
