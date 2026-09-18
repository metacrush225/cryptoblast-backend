"""Route de test manuel des alertes Discord et d'analyse IA."""

import base64
import logging

import pandas as pd
from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import ALERTS_SCHEDULER_TOKEN, DISCORD_ENABLED, GEMINI_ENABLED
from app.services.ai_analysis import analyze_chart_and_data
from app.services.alerts import check_rsi_and_alert

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["Alerts"])


class ChartAnalysisRequest(BaseModel):
    symbol: str
    image_base64: str | None = None
    recent_data: list[dict] | None = None


@router.post("/scheduler-check")
async def scheduler_check(request: Request, x_scheduler_token: str | None = Header(default=None)):
    """Déclenche un check unique depuis Google Cloud Scheduler."""
    if not ALERTS_SCHEDULER_TOKEN or x_scheduler_token != ALERTS_SCHEDULER_TOKEN:
        return JSONResponse(status_code=401, content={"success": False, "message": "Token invalide"})
    if not DISCORD_ENABLED:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "DISCORD_BOT_TOKEN / DISCORD_ALERT_CHANNEL_ID non configurés"},
        )

    await check_rsi_and_alert(request.app.state.http_client)
    return {"success": True, "message": "Vérification RSI terminée"}


@router.post("/test")
async def test_discord_alert(request: Request):
    """Déclenche manuellement un check RSI + alerte Discord (utile pour tester la config)."""
    if not DISCORD_ENABLED:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "DISCORD_BOT_TOKEN / DISCORD_ALERT_CHANNEL_ID non configurés"},
        )
    await check_rsi_and_alert(request.app.state.http_client)
    return {"success": True, "message": "Vérification RSI déclenchée, alerte envoyée si seuils dépassés"}


@router.post("/analyze-chart")
async def analyze_chart(request: ChartAnalysisRequest):
    """Analyse un graphique PNG avec Gemini en fournissant le contexte technique du symbole."""
    if not GEMINI_ENABLED:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "GEMINI_API_KEY non configurée"},
        )

    image_bytes = None

    if request.image_base64:
        try:
            image_bytes = base64.b64decode(request.image_base64)
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "image_base64 invalide"},
            )

        if not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "image_base64 ne contient pas un PNG valide"},
            )

    try:
        recent_df = pd.DataFrame(request.recent_data or [])
        if not recent_df.empty:
            for col in ["close", "rsi", "sma_10", "sma_30"]:
                if col in recent_df.columns:
                    recent_df[col] = pd.to_numeric(recent_df[col], errors="coerce")

        analysis = await analyze_chart_and_data(
            image_bytes=image_bytes,
            symbol=request.symbol.upper(),
            df_last_candles=recent_df,
        )

        return {
            "success": True,
            "symbol": request.symbol.upper(),
            "analysis": analysis,
        }
    except Exception as exc:
        logger.exception("Erreur lors de l'analyse du graphique via Gemini")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Erreur d'analyse IA: {exc}"},
        )
