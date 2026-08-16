"""Génération de graphiques (close + SMA10/30) en PNG, en mémoire."""

from datetime import datetime
from io import BytesIO

import pandas as pd
import matplotlib
matplotlib.use("Agg")  # backend non-interactif, pas d'affichage requis côté serveur
import matplotlib.pyplot as plt

from app.config import SYMBOL_NAMES


def generate_chart_png(symbol: str, klines: list) -> bytes:
    closes = [float(k[4]) for k in klines]
    times = [datetime.fromtimestamp(k[0] / 1000) for k in klines]

    s = pd.Series(closes, dtype=float)
    sma10 = s.rolling(10).mean()
    sma30 = s.rolling(30).mean()

    fig, ax = plt.subplots(figsize=(8, 4), dpi=120)
    ax.plot(times, closes, label="Close", color="#5865F2", linewidth=1.5)
    if sma10.notna().any():
        ax.plot(times, sma10, label="SMA10", color="#57F287", linewidth=1, linestyle="--")
    if sma30.notna().any():
        ax.plot(times, sma30, label="SMA30", color="#ED4245", linewidth=1, linestyle="--")

    ax.set_title(f"{SYMBOL_NAMES.get(symbol, symbol)} ({symbol})")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(alpha=0.2)
    fig.autofmt_xdate()
    fig.tight_layout()

    buf = BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
