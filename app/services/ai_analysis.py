import logging

import pandas as pd
from google import genai
from google.genai import types

from app.config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)


client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


async def analyze_chart_and_data(image_bytes: bytes | None, symbol: str, df_last_candles: pd.DataFrame | None = None):
    """Analyse un graphique crypto avec Gemini en utilisant les 10 dernières données techniques."""
    if not GEMINI_API_KEY or client is None:
        raise ValueError("GEMINI_API_KEY non configurée")

    if image_bytes is not None:
        if not isinstance(image_bytes, (bytes, bytearray)) or len(image_bytes) < 8:
            raise ValueError("Le payload image est vide ou invalide.")

        png_signature = b"\x89PNG\r\n\x1a\n"
        if not bytes(image_bytes).startswith(png_signature):
            raise ValueError("L'image fournie n'est pas un PNG valide.")

    if df_last_candles is None:
        df_last_candles = pd.DataFrame()

    if not df_last_candles.empty:
        relevant_columns = [col for col in ["close", "rsi", "sma_10", "sma_30"] if col in df_last_candles.columns]
        if relevant_columns:
            recent_data_str = df_last_candles[relevant_columns].tail(10).to_string(index=False)
        else:
            recent_data_str = df_last_candles.tail(10).to_string(index=False)
    else:
        recent_data_str = "Aucune donnée technique fournie par le backend."

    prompt = f"""
    Tu es un expert en analyse technique de marché crypto.

    Analyse le graphique ci-joint pour {symbol} ainsi que les 10 dernières données calculées localement :
    {recent_data_str}

    Instructions :
    1. Observe la forme des bougies sur le graphique (mèches, structures d'hésitation ou de rejet).
    2. Identifie si le RSI bas s'accompagne d'une divergence ou d'une perte de momentum vendeur.
    3. Donne une analyse concise pour Discord (3 puces max) :
       - **Action du prix** : Structure visuelle / tendance immédiate.
       - **Niveau clé** : Support/Résistance technique identifiable sur le graphique.
       - **Signal** : Probabilité de rebond ou risque de continuation baissière.

    Sois précis, synthétique et direct. Pas de disclaimer.
    """

    try:
        contents = [prompt]
        if image_bytes is not None:
            contents.append(
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type="image/png",
                )
            )

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
        )

        text = getattr(response, "text", None)
        if text:
            return text.strip()

        candidates = getattr(response, "candidates", [])
        if candidates:
            parts = getattr(candidates[0].content, "parts", [])
            if parts:
                texts = []
                for part in parts:
                    if hasattr(part, "text") and part.text:
                        texts.append(part.text)
                if texts:
                    return "\n".join(texts).strip()

        raise ValueError("Réponse Gemini vide ou non exploitable")
    except Exception as exc:
        logger.exception("Erreur lors de l'analyse Gemini")
        raise RuntimeError(f"Échec de l'analyse IA: {exc}") from exc
