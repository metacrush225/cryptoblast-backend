from datetime import datetime
from io import BytesIO

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from app.config import SYMBOL_NAMES


# ============================================================
# SIGNAL
# ============================================================

def get_signal_from_rsi(rsi: float | None) -> str:

    print(f"DEBUG: rsi = {rsi}")

    if rsi is None:
        return "neutral"

    rsi = round(float(rsi), 2)

    if rsi <= 30:
        return "oversold"

    if rsi >= 70:
        return "overbought"

    return "neutral"


def _get_signal_theme(signal: str | None):
    normalized = (signal or "neutral").strip().lower()

    print(f"DEBUG: signal = {signal}")
    print(f"DEBUG: normalized signal = {normalized}")

    if normalized in ("oversold", "survente"):
        return {
            "label": "SURVENTE",
            "color": "#FF4D5E",
            "bg": "#211317",
            "border": "#6C2831",
        }

    if normalized in ("overbought", "surachat"):
        return {
            "label": "SURACHAT",
            "color": "#00D488",
            "bg": "#0F1C17",
            "border": "#1F5A46",
        }

    return {
        "label": "NEUTRE",
        "color": "#D9A94A",
        "bg": "#201B10",
        "border": "#5E4A20",
    }


# ============================================================
# ANALYSE TECHNIQUE SIMPLE
# ============================================================

def get_trend_comment(
    close: float,
    sma10: float | None,
    sma30: float | None,
) -> str:

    if sma10 is None or sma30 is None:
        return "Pas encore assez de données pour déterminer la tendance."

    if close > sma10 > sma30:
        return (
            "📈 **Tendance haussière** : "
            "le prix évolue au-dessus des SMA 10 et SMA 30."
        )

    if close < sma10 < sma30:
        return (
            "📉 **Tendance baissière** : "
            "le prix évolue sous les SMA 10 et SMA 30."
        )

    if close > sma10 and sma10 < sma30:
        return (
            "🔄 **Rebond possible** : "
            "le prix repasse au-dessus de la SMA 10, "
            "mais la structure reste fragile."
        )

    if close < sma10 and sma10 > sma30:
        return (
            "⚠️ **Essoufflement possible** : "
            "le prix repasse sous la SMA 10 malgré une structure "
            "encore globalement haussière."
        )

    return "⚖️ **Structure de marché mixte**."


# ============================================================
# MESSAGE DISCORD
# ============================================================

def build_discord_alert_message(
    symbol: str,
    rsi_value: float,
    close: float,
    sma10: float | None = None,
    sma30: float | None = None,
    variation_pct: float | None = None,
) -> str:

    name = SYMBOL_NAMES.get(symbol, symbol)

    signal = get_signal_from_rsi(rsi_value)
    trend = get_trend_comment(close, sma10, sma30)

    if signal == "oversold":
        title = f"⚠️ Oversold : {name}"

        explanation = (
            f"Le RSI de **{name}** est passé sous le seuil de **30**, "
            "ce qui place le marché en zone de **survente**."
        )

        watch = (
            "👀 **À surveiller**\n"
            "• retour du RSI au-dessus de 30\n"
            "• stabilisation du prix\n"
            "• reprise de la SMA 10\n"
            "• éventuel retournement du momentum"
        )

    elif signal == "overbought":
        title = f"⚠️ Overbought : {name}"

        explanation = (
            f"Le RSI de **{name}** est passé au-dessus du seuil de **70**, "
            "ce qui place le marché en zone de **surachat**."
        )

        watch = (
            "👀 **À surveiller**\n"
            "• retour du RSI sous 70\n"
            "• passage du prix sous la SMA 10\n"
            "• ralentissement de la hausse\n"
            "• éventuelle prise de bénéfices"
        )

    else:
        title = f"ℹ️ Momentum neutre : {name}"

        explanation = (
            f"Le RSI de **{name}** évolue actuellement dans une zone neutre."
        )

        watch = (
            "👀 **À surveiller**\n"
            "• RSI sous 30 ou au-dessus de 70\n"
            "• croisement SMA 10 / SMA 30\n"
            "• accélération du prix"
        )

    variation_line = ""

    if variation_pct is not None:
        variation_line = f"\nVariation observée : **{variation_pct:+.2f}%**"

    return (
        f"## {title}\n\n"
        f"{explanation}\n\n"
        f"**RSI actuel : {rsi_value:.2f}**\n"
        f"Prix actuel : **{format_price(close)} USDT**"
        f"{variation_line}\n\n"
        f"{trend}\n\n"
        f"{watch}\n\n"
        "⚠️ *Signal technique informatif, pas un conseil financier.*"
    )

# --------------------------------------------------------
# Format prix
# --------------------------------------------------------

def format_price(price: float) -> str:
    if price >= 100:
        return f"{price:,.2f}"
    if price >= 1:
        return f"{price:.4f}"
    if price >= 0.01:
        return f"{price:.6f}"
    return f"{price:.8f}"

# ============================================================
# GRAPHIQUE
# ============================================================

def generate_chart_png(
    symbol: str,
    klines: list,
    rsi_value: float,
) -> bytes:

    if not klines:
        raise ValueError("Impossible de générer le graphique : klines vide.")

    closes = [float(k[4]) for k in klines]

    times = [
        datetime.fromtimestamp(k[0] / 1000)
        for k in klines
    ]

    series = pd.Series(closes, dtype=float)

    sma10 = series.rolling(10).mean()
    sma30 = series.rolling(30).mean()

    # --------------------------------------------------------
    # IMPORTANT :
    # si aucun signal n'est fourni, on utilise directement
    # le RSI pour éviter les incohérences Discord / graphique.
    # --------------------------------------------------------

    signal = get_signal_from_rsi(rsi_value)
    theme = _get_signal_theme(signal)

    # --------------------------------------------------------
    # Theme
    # --------------------------------------------------------

    BG = "#0A0B0D"
    SURFACE = "#131418"
    SURFACE_ELEVATED = "#17181D"

    BORDER = "#24262B"
    GRID = "#2B2E35"

    TEXT_PRIMARY = "#F2F3F5"
    TEXT_SECONDARY = "#8A8F98"
    TEXT_TERTIARY = "#5C6068"

    CLOSE_BLUE = "#2EA8FF"
    SMA10_GOLD = "#D9A94A"
    SMA30_RED = "#FF4D5E"

    # --------------------------------------------------------
    # Stats
    # --------------------------------------------------------

    last_close = closes[-1]
    first_close = closes[0]

    variation_pct = (
        ((last_close - first_close) / first_close) * 100
        if first_close
        else 0.0
    )

    friendly_name = SYMBOL_NAMES.get(symbol, symbol)

    # --------------------------------------------------------
    # Figure
    # --------------------------------------------------------

    fig, ax = plt.subplots(
        figsize=(10, 5.2),
        dpi=140,
    )

    fig.patch.set_facecolor(BG)
    ax.set_facecolor(SURFACE)

    # --------------------------------------------------------
    # Close
    # --------------------------------------------------------

    ax.plot(
        times,
        closes,
        label="Close",
        color=CLOSE_BLUE,
        linewidth=2.0,
        solid_capstyle="round",
        zorder=3,
    )

    # --------------------------------------------------------
    # SMA 10
    # --------------------------------------------------------

    if sma10.notna().any():
        ax.plot(
            times,
            sma10,
            label="SMA 10",
            color=SMA10_GOLD,
            linewidth=1.8,
            alpha=0.95,
            zorder=2,
        )

    # --------------------------------------------------------
    # SMA 30
    # --------------------------------------------------------

    if sma30.notna().any():
        ax.plot(
            times,
            sma30,
            label="SMA 30",
            color=SMA30_RED,
            linewidth=1.8,
            alpha=0.95,
            zorder=2,
        )

    # --------------------------------------------------------
    # Zone sous la courbe
    # --------------------------------------------------------

    price_range = max(closes) - min(closes)

    baseline = min(closes) - price_range * 0.05

    ax.fill_between(
        times,
        closes,
        baseline,
        color=CLOSE_BLUE,
        alpha=0.06,
        zorder=1,
    )

    # --------------------------------------------------------
    # Dernier prix
    # --------------------------------------------------------

    last_time = times[-1]

    ax.scatter(
        [last_time],
        [last_close],
        s=34,
        color=CLOSE_BLUE,
        edgecolor=TEXT_PRIMARY,
        linewidth=0.8,
        zorder=5,
    )

    # On adapte l'affichage aux cryptos très peu chères
    if last_close >= 100:
        price_label = f"{last_close:,.2f}"
    elif last_close >= 1:
        price_label = f"{last_close:.4f}"
    else:
        price_label = f"{last_close:.6f}"

    ax.annotate(
        price_label,
        xy=(last_time, last_close),
        xytext=(10, 0),
        textcoords="offset points",
        color=TEXT_PRIMARY,
        fontsize=8,
        va="center",
        bbox=dict(
            boxstyle="round,pad=0.28",
            facecolor=SURFACE_ELEVATED,
            edgecolor=BORDER,
            linewidth=1,
            alpha=0.98,
        ),
    )

    # --------------------------------------------------------
    # Axes
    # --------------------------------------------------------

    ax.grid(
        True,
        color=GRID,
        alpha=0.45,
        linewidth=0.8,
    )

    ax.set_axisbelow(True)

    for spine in ax.spines.values():
        spine.set_color(BORDER)
        spine.set_linewidth(1)

    ax.tick_params(
        axis="x",
        colors=TEXT_SECONDARY,
        labelsize=8,
    )

    ax.tick_params(
        axis="y",
        colors=TEXT_SECONDARY,
        labelsize=8,
    )

    # --------------------------------------------------------
    # Dates
    # --------------------------------------------------------

    locator = mdates.AutoDateLocator(
        minticks=4,
        maxticks=7,
    )

    formatter = mdates.ConciseDateFormatter(locator)

    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(formatter)

    # --------------------------------------------------------
    # Format prix axis
    # --------------------------------------------------------

    def format_price_axis(value, _):
        if last_close >= 100:
            return f"{value:,.0f}"

        if last_close >= 1:
            return f"{value:.2f}"

        return f"{value:.4f}"

    ax.yaxis.set_major_formatter(
        plt.FuncFormatter(format_price_axis)
    )

    ax.margins(
        x=0.02,
        y=0.10,
    )



    # --------------------------------------------------------
    # Legend
    # --------------------------------------------------------

    legend = ax.legend(
        loc="upper left",
        fontsize=8,
        frameon=True,
        facecolor=SURFACE,
        edgecolor=BORDER,
        borderpad=0.6,
    )

    for text in legend.get_texts():
        text.set_color(TEXT_PRIMARY)

    # --------------------------------------------------------
    # Header
    # --------------------------------------------------------

    fig.text(
        0.055,
        0.955,
        friendly_name.upper(),
        color=TEXT_SECONDARY,
        fontsize=8,
        fontweight="bold",
        va="top",
        ha="left",
    )

    fig.text(
        0.055,
        0.918,
        symbol,
        color=TEXT_PRIMARY,
        fontsize=15,
        fontweight="bold",
        va="top",
        ha="left",
    )

    # --------------------------------------------------------
    # Sous-titre
    # --------------------------------------------------------

    subtitle_parts = []

    if rsi_value is not None:
        subtitle_parts.append(
            f"RSI {rsi_value:.2f}"
        )

    subtitle_parts.append(
        f"Close {price_label}"
    )

    subtitle_parts.append(
        f"Var {variation_pct:+.2f}%"
    )

    fig.text(
        0.055,
        0.882,
        "  •  ".join(subtitle_parts),
        color=TEXT_SECONDARY,
        fontsize=9,
        va="top",
        ha="left",
    )

    # --------------------------------------------------------
    # Badge signal
    # --------------------------------------------------------

    fig.text(
        0.94,
        0.935,
        theme["label"],
        color=theme["color"],
        fontsize=9,
        fontweight="bold",
        va="center",
        ha="right",
        bbox=dict(
            boxstyle="round,pad=0.35",
            facecolor=theme["bg"],
            edgecolor=theme["border"],
            linewidth=1,
        ),
    )

    # --------------------------------------------------------
    # Timestamp
    # --------------------------------------------------------

    fig.text(
        0.94,
        0.885,
        datetime.now().strftime(
            "Généré le %d/%m/%Y %H:%M"
        ),
        color=TEXT_TERTIARY,
        fontsize=8,
        va="top",
        ha="right",
    )

    # --------------------------------------------------------
    # Layout
    # --------------------------------------------------------

    plt.subplots_adjust(
        top=0.78,
        left=0.07,
        right=0.97,
        bottom=0.15,
    )

    buf = BytesIO()

    fig.savefig(
        buf,
        format="png",
        facecolor=fig.get_facecolor(),
        bbox_inches="tight",
        pad_inches=0.18,
    )

    plt.close(fig)

    buf.seek(0)

    return buf.read()