"""Exotel webhook routes for status callbacks."""

from typing import Dict

from fastapi import APIRouter, Request
from loguru import logger

router = APIRouter()


@router.post("/webhook")
async def exotel_status_callback(request: Request):
    """Handle Exotel status callback webhooks.

    Exotel sends status updates (ringing, in-progress, completed, etc.)
    to this endpoint during and after calls.
    """
    # Exotel can send form-encoded or JSON
    content_type = request.headers.get("content-type", "")
    if "json" in content_type:
        data = await request.json()
    else:
        form = await request.form()
        data = dict(form)

    logger.info(f"Exotel status callback: {data.get('Status', 'unknown')} "
                f"for call {data.get('CallSid', 'unknown')}")

    # Import here to avoid circular imports
    from api.services.telephony.status_processor import process_status_callback

    await process_status_callback("exotel", data, dict(request.query_params))

    return {"status": "ok"}


@router.post("/answer")
async def exotel_answer_callback(request: Request):
    """Handle Exotel answer URL callback.

    This is called when Exotel needs instructions on how to handle a call.
    For the Voicebot applet, this is typically configured in the Exotel dashboard
    rather than via API response.
    """
    data = dict(await request.form()) if "form" in request.headers.get("content-type", "") else await request.json()

    logger.info(f"Exotel answer callback: {data}")

    # Return empty response — Exotel Voicebot applet handles routing
    return {"status": "ok"}
