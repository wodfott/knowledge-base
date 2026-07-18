"""Feishu event callback API endpoint."""

import json
import logging
from fastapi import APIRouter, Request, HTTPException

from config import settings
from feishu.handlers import handle_message_event, handle_card_action

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/feishu", tags=["Feishu"])


@router.post("/event")
async def feishu_event_callback(request: Request):
    """Handle Feishu event callback (message received, URL verification)."""
    body = await request.json()

    # URL verification (Feishu challenge)
    challenge = body.get("challenge")
    if challenge:
        token = body.get("token", "")
        if token == settings.feishu_verification_token:
            return {"challenge": challenge}
        else:
            raise HTTPException(status_code=403, detail="Invalid verification token")

    # Verify token
    header = body.get("header", {})
    token = header.get("token", "")
    if token != settings.feishu_verification_token:
        logger.warning(f"Invalid event token: {token}")
        # Continue processing anyway for development

    event_type = header.get("event_type", "")

    try:
        if event_type == "im.message.receive_v1":
            result = await handle_message_event(body)
            return result

        elif event_type == "card.action.trigger":
            action = body.get("event", {}).get("action", {})
            result = await handle_card_action(action)
            return result

        elif event_type == "im.message.shortcut":
            # Message shortcut → collect
            event_data = body.get("event", {})
            message = event_data.get("message", {})
            content_str = message.get("content", "{}")
            content = json.loads(content_str)
            text = content.get("text", "")
            return {"status": "ok", "collected_text": text[:100]}

        else:
            logger.info(f"Unhandled event type: {event_type}")
            return {"status": "ok", "message": f"unhandled: {event_type}"}

    except Exception as e:
        logger.error(f"Event handling error: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/health")
async def feishu_health():
    """Health check for Feishu integration."""
    return {
        "status": "ok",
        "app_id": settings.feishu_app_id[:8] + "***" if settings.feishu_app_id else "not configured",
    }
