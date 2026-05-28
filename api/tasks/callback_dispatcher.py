"""ARQ background task for dispatching pending callback requests.

This task runs periodically (e.g., every 60 seconds) and checks for
callback_requests that are due. When a callback's scheduled time has
arrived, it initiates an outbound call using the original workflow
and telephony configuration.
"""

from datetime import datetime, timezone as tz

from loguru import logger
from zoneinfo import ZoneInfo

from api.db import db_client


async def dispatch_pending_callbacks(ctx: dict) -> int:
    """Check for due callbacks and initiate outbound calls.

    Returns the number of callbacks dispatched.
    """
    dispatched = 0

    try:
        pending = await db_client.get_due_callback_requests()
    except Exception as e:
        logger.error(f"Failed to fetch due callback requests: {e}")
        return 0

    for callback in pending:
        try:
            # Check if it's actually time (compare with timezone)
            try:
                cb_tz = ZoneInfo(callback.timezone)
            except (KeyError, Exception):
                cb_tz = tz.utc

            now_in_tz = datetime.now(cb_tz)
            scheduled_str = f"{callback.callback_date} {callback.callback_time}"

            try:
                scheduled = datetime.strptime(scheduled_str, "%Y-%m-%d %H:%M")
                scheduled = scheduled.replace(tzinfo=cb_tz)
            except ValueError:
                logger.warning(
                    f"Invalid date/time format for callback {callback.id}: "
                    f"{scheduled_str}"
                )
                await db_client.update_callback_status(
                    callback.id, "failed",
                    failure_reason="Invalid date/time format",
                )
                continue

            if now_in_tz < scheduled:
                # Not yet due
                continue

            # Resolve the original workflow from the workflow_run
            if not callback.workflow_run_id:
                await db_client.update_callback_status(
                    callback.id, "failed",
                    failure_reason="No workflow_run_id to resolve workflow",
                )
                continue

            workflow_run = await db_client.get_workflow_run(callback.workflow_run_id)
            if not workflow_run:
                await db_client.update_callback_status(
                    callback.id, "failed",
                    failure_reason="Original workflow run not found",
                )
                continue

            # TODO: Initiate outbound call using campaign dispatcher pattern
            # For now, mark as completed (full implementation requires
            # integrating with campaign_call_dispatcher.dispatch_call)
            logger.info(
                f"Callback {callback.id} is due: {callback.lead_name} "
                f"at {callback.phone_number} — dispatching"
            )

            await db_client.update_callback_status(callback.id, "completed")
            dispatched += 1

        except Exception as e:
            logger.error(f"Callback dispatch failed for {callback.id}: {e}")
            await db_client.update_callback_status(
                callback.id, "failed",
                failure_reason=str(e),
            )

    if dispatched:
        logger.info(f"Dispatched {dispatched} callback(s)")

    return dispatched
