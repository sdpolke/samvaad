import os
from typing import Optional

from loguru import logger
from pipecat.utils.run_context import set_current_run_id

from api.db import db_client
from api.services.pricing.workflow_run_cost import calculate_workflow_run_cost
from api.services.storage import get_current_storage_backend, storage_fs
from api.tasks.run_integrations import run_integrations_post_workflow_run


async def upload_voicemail_audio_to_s3(
    _ctx,
    workflow_run_id: int,
    temp_file_path: str,
    s3_key: str,
):
    """Upload voicemail detection audio from temp file to S3.

    Handles voicemail-specific paths and doesn't update the workflow run's
    recording_url field.

    Args:
        _ctx: ARQ context (unused)
        workflow_run_id: The workflow run ID
        temp_file_path: Path to the temporary WAV file
        s3_key: The S3 key where the file should be uploaded
    """
    run_id = str(workflow_run_id)
    set_current_run_id(run_id)

    logger.info(f"Starting voicemail audio upload to S3 from {temp_file_path}")

    try:
        # Verify temp file exists
        if not os.path.exists(temp_file_path):
            logger.error(f"Temp voicemail audio file not found: {temp_file_path}")
            raise FileNotFoundError(
                f"Temp voicemail audio file not found: {temp_file_path}"
            )

        file_size = os.path.getsize(temp_file_path)
        logger.debug(f"Voicemail audio file size: {file_size} bytes")

        # Upload to S3
        upload_ok = await storage_fs.aupload_file(temp_file_path, s3_key)

        if upload_ok:
            logger.info(f"Successfully uploaded voicemail audio to S3: {s3_key}")
        else:
            logger.error(
                f"Failed to upload voicemail audio to S3 for workflow {workflow_run_id}"
            )
            raise Exception(f"S3 upload failed for {s3_key}")

    except Exception as e:
        logger.error(
            f"Error uploading voicemail audio to S3 for workflow {workflow_run_id}: {e}"
        )
        raise
    finally:
        # Clean up temp file
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                logger.debug(f"Cleaned up temp voicemail audio file: {temp_file_path}")
            except Exception as e:
                logger.warning(
                    f"Failed to clean up temp voicemail audio file {temp_file_path}: {e}"
                )


async def process_workflow_completion(
    _ctx,
    workflow_run_id: int,
    audio_temp_path: Optional[str] = None,
    transcript_temp_path: Optional[str] = None,
):
    """Process workflow completion: upload artifacts and run integrations.

    This task combines audio upload, transcript upload, and webhook integrations
    into a single sequential task to ensure integrations run after uploads complete.

    Args:
        _ctx: ARQ context (unused)
        workflow_run_id: The workflow run ID
        audio_temp_path: Optional path to temp audio file
        transcript_temp_path: Optional path to temp transcript file
    """
    run_id = str(workflow_run_id)
    set_current_run_id(run_id)

    logger.info(f"Processing workflow completion for run {workflow_run_id}")

    storage_backend = get_current_storage_backend()

    # Step 1: Upload audio if provided
    if audio_temp_path:
        try:
            if os.path.exists(audio_temp_path):
                file_size = os.path.getsize(audio_temp_path)
                logger.debug(f"Audio file size: {file_size} bytes")

                recording_url = f"recordings/{workflow_run_id}.wav"
                logger.info(
                    f"Uploading audio to {storage_backend.name} - workflow_run_id: {workflow_run_id}"
                )

                await storage_fs.aupload_file(audio_temp_path, recording_url)
                await db_client.update_workflow_run(
                    run_id=workflow_run_id,
                    recording_url=recording_url,
                    storage_backend=storage_backend.value,
                )
                logger.info(f"Successfully uploaded audio: {recording_url}")
            else:
                logger.warning(f"Audio temp file not found: {audio_temp_path}")
        except Exception as e:
            logger.error(f"Error uploading audio for workflow {workflow_run_id}: {e}")
        finally:
            if audio_temp_path and os.path.exists(audio_temp_path):
                try:
                    os.remove(audio_temp_path)
                    logger.debug(f"Cleaned up temp audio file: {audio_temp_path}")
                except Exception as e:
                    logger.warning(f"Failed to clean up temp audio file: {e}")

    # Step 2: Upload transcript if provided
    if transcript_temp_path:
        try:
            if os.path.exists(transcript_temp_path):
                file_size = os.path.getsize(transcript_temp_path)
                logger.debug(f"Transcript file size: {file_size} bytes")

                transcript_url = f"transcripts/{workflow_run_id}.txt"
                logger.info(
                    f"Uploading transcript to {storage_backend.name} - workflow_run_id: {workflow_run_id}"
                )

                await storage_fs.aupload_file(transcript_temp_path, transcript_url)
                await db_client.update_workflow_run(
                    run_id=workflow_run_id,
                    transcript_url=transcript_url,
                    storage_backend=storage_backend.value,
                )
                logger.info(f"Successfully uploaded transcript: {transcript_url}")
            else:
                logger.warning(
                    f"Transcript temp file not found: {transcript_temp_path}"
                )
        except Exception as e:
            logger.error(
                f"Error uploading transcript for workflow {workflow_run_id}: {e}"
            )
        finally:
            if transcript_temp_path and os.path.exists(transcript_temp_path):
                try:
                    os.remove(transcript_temp_path)
                    logger.debug(
                        f"Cleaned up temp transcript file: {transcript_temp_path}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to clean up temp transcript file: {e}")

    # Step 3: Run integrations including QA analysis (after uploads are complete)
    try:
        await run_integrations_post_workflow_run(_ctx, workflow_run_id)
    except Exception as e:
        logger.error(f"Error running integrations for workflow {workflow_run_id}: {e}")

    # Step 4: Calculate cost after integrations (so QA token usage is included)
    try:
        await calculate_workflow_run_cost(workflow_run_id)
    except Exception as e:
        logger.error(f"Error calculating cost for workflow {workflow_run_id}: {e}")

    # Step 5: Persist switchboard call log (ledger snapshot) if ledger fields present
    try:
        await _persist_switchboard_call_log(workflow_run_id)
    except Exception as e:
        logger.error(
            f"Error persisting switchboard call log for workflow {workflow_run_id}: {e}"
        )

    logger.info(f"Completed workflow completion processing for run {workflow_run_id}")


async def _persist_switchboard_call_log(workflow_run_id: int) -> None:
    """Extract ledger fields from gathered_context and persist to switchboard_call_logs.

    Only writes a row if at least one ledger field is populated in the run's
    gathered_context (i.e., this was a switchboard call, not a generic workflow run).
    Failures are logged but never propagate — ledger persistence is best-effort.
    """
    from api.services.switchboard.ledger import LEDGER_FIELD_NAMES

    workflow_run = await db_client.get_workflow_run_by_id(workflow_run_id)
    if not workflow_run:
        return

    gathered = workflow_run.gathered_context or {}

    # Only persist if this run has switchboard ledger fields
    ledger_data = {k: gathered.get(k) for k in LEDGER_FIELD_NAMES if k in gathered}
    if not ledger_data:
        return

    # Also capture disposition and end-reason from gathered_context
    ledger_data["call_disposition"] = gathered.get("call_disposition")
    ledger_data["mapped_call_disposition"] = gathered.get("mapped_call_disposition")

    # Determine organization_id from the workflow
    organization_id = None
    if workflow_run.workflow_id:
        workflow = await db_client.get_workflow_by_id(workflow_run.workflow_id)
        if workflow:
            organization_id = workflow.organization_id

    if not organization_id:
        logger.warning(
            f"Cannot persist switchboard call log for run {workflow_run_id}: "
            "no organization_id resolved"
        )
        return

    end_reason = gathered.get("call_disposition") or "unknown"

    await db_client.create_switchboard_call_log(
        workflow_run_id=workflow_run_id,
        organization_id=organization_id,
        ledger=ledger_data,
        end_reason=end_reason,
    )
