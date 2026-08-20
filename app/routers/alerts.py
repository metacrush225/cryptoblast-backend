"""Route de test manuel des alertes Discord."""

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from app.config import ALERTS_SCHEDULER_TOKEN, DISCORD_ENABLED
from app.services.alerts import check_rsi_and_alert

router = APIRouter(prefix="/api/alerts", tags=["Alerts"])


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
