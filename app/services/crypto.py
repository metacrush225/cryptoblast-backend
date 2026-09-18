"""Logique métier : indicateurs techniques (RSI, SMA, EMA, MACD, ATR) et agrégation des données crypto."""

from datetime import datetime

import pandas as pd

from app.clients.binance import BinanceClient
from app.models.crypto_data import CryptoData


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


def calculate_ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def calculate_macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal_period: int = 9
) -> tuple[pd.Series, pd.Series]:
    ema_fast = calculate_ema(series, fast)
    ema_slow = calculate_ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal_period)
    return macd_line, signal_line


def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(window=period, min_periods=period).mean()


def _last_or_none(series: pd.Series, min_len: int) -> float | None:
    if len(series) >= min_len and not pd.isna(series.iloc[-1]):
        return float(series.iloc[-1])
    return None

async def build_crypto_data(binance: BinanceClient, symbol: str) -> CryptoData:
    ticker_data = await binance.get_24h_ticker(symbol)
    # 100 bougies pour stabiliser EMA21/MACD/signal (26+9)
    klines = await binance.get_klines(symbol, "1h", 100)

    highs = pd.Series([float(k[2]) for k in klines], dtype=float)
    lows = pd.Series([float(k[3]) for k in klines], dtype=float)
    closes = pd.Series([float(k[4]) for k in klines], dtype=float)
    volumes = pd.Series([float(k[5]) for k in klines], dtype=float)

    rsi = calculate_rsi(closes.tolist())

    sma10_series = rolling_sma(closes, 10)
    sma30_series = rolling_sma(closes, 30)
    volume_ma20_series = rolling_sma(volumes, 20)
    ema9_series = calculate_ema(closes, 9)
    ema21_series = calculate_ema(closes, 21)
    macd_series, signal_series = calculate_macd(closes)
    atr14_series = calculate_atr(highs, lows, closes, 14)

    return CryptoData(
        symbol=symbol,
        open=float(ticker_data["openPrice"]),
        close=float(ticker_data["lastPrice"]),
        rsi=round(rsi, 2),
        timestamp=datetime.now().isoformat(),
        price_change_24h=float(ticker_data["priceChangePercent"]),
        volume_24h=float(ticker_data["volume"]),
        sma10=_last_or_none(sma10_series, 10),
        sma30=_last_or_none(sma30_series, 30),
        volume_ma_20=_last_or_none(volume_ma20_series, 20),
        ema_9=_last_or_none(ema9_series, 9),
        ema_21=_last_or_none(ema21_series, 21),
        macd=_last_or_none(macd_series, 26),
        signal=_last_or_none(signal_series, 35),
        atr_14=_last_or_none(atr14_series, 15),
    )