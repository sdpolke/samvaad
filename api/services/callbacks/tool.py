"""Callback scheduling tool for voice agent pipelines.

Provides the LLM tool schema and handler for scheduling follow-up calls
during a conversation. When the user requests a callback, the LLM invokes
this tool to persist the request to the database.
"""

from loguru import logger


SCHEDULE_CALLBACK_SCHEMA = {
    "type": "function",
    "function": {
        "name": "schedule_callback",
        "description": (
            "Schedule a callback when the user is busy or wants to be contacted later. "
            "Use this when the user says they are busy, want to be called back, "
            "need time to think, or want to schedule a follow-up call."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "The date for the callback in YYYY-MM-DD format",
                },
                "time": {
                    "type": "string",
                    "description": "The preferred time for the callback in HH:MM format",
                },
                "timezone": {
                    "type": "string",
                    "description": "The user's timezone (IANA format, e.g. 'America/New_York')",
                },
                "reason": {
                    "type": "string",
                    "description": "Optional reason for the callback or context from the conversation",
                },
            },
            "required": ["date", "time", "timezone"],
        },
    },
}


async def handle_schedule_callback(
    args: dict,
    organization_id: int,
    workflow_run_id: int,
    campaign_id: int | None = None,
    phone_number: str = "",
    lead_name: str | None = None,
    company: str | None = None,
) -> str:
    """Create a callback request record in the database.

    Args:
        args: Tool arguments from the LLM (date, time, timezone, reason)
        organization_id: Owning organization
        workflow_run_id: Source conversation run
        campaign_id: Associated campaign (if any)
        phone_number: Lead's phone number from initial_context
        lead_name: Lead name from initial_context
        company: Company name from initial_context

    Returns:
        Confirmation message string for the LLM to relay to the user.
    """
    from api.db import db_client

    date = args.get("date", "")
    time_val = args.get("time", "")
    timezone = args.get("timezone", "")
    reason = args.get("reason", "")

    if not phone_number:
        logger.warning(
            f"schedule_callback invoked without phone_number for run {workflow_run_id}"
        )
        return "Could not schedule callback — no phone number available."

    if not date or not time_val or not timezone:
        return "Could not schedule callback — date, time, and timezone are required."

    try:
        callback = await db_client.create_callback_request(
            organization_id=organization_id,
            workflow_run_id=workflow_run_id,
            campaign_id=campaign_id,
            lead_name=lead_name,
            phone_number=phone_number,
            company=company,
            callback_date=date,
            callback_time=time_val,
            timezone=timezone,
            reason=reason,
        )
        logger.info(
            f"Callback scheduled: {lead_name} on {date} at {time_val} {timezone} "
            f"(id={callback.id})"
        )
        return (
            f"Callback scheduled for {date} at {time_val} {timezone}. "
            f"We'll call you back then!"
        )
    except Exception as e:
        logger.error(f"Failed to create callback request: {e}")
        return "Could not save the callback. Please try again."
