from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from loguru import logger

from api.db import db_client
from api.services.integrations.base import IntegrationCompletionContext
from api.utils.credential_auth import build_auth_header

from .client import TwentyClient, TwentyClientConfig
from .mapping import (
    build_render_context,
    render_fields,
    resolve_object_name,
    resolve_record_id,
)
from .node import TwentyNodeData


async def run_completion(
    nodes: list[dict[str, Any]],
    context: IntegrationCompletionContext,
) -> dict[str, Any]:
    """Write the completed call outcome back into Twenty for each Twenty node."""
    results: dict[str, Any] = {}
    render_context: dict[str, Any] | None = None

    for node in nodes:
        node_id = node.get("id", "unknown")
        result_key = f"twenty_{node_id}"

        try:
            data = TwentyNodeData.model_validate(node.get("data", {}))
        except Exception as exc:
            logger.warning(f"Twenty node #{node_id} failed validation, skipping: {exc}")
            results[result_key] = {"error": "validation_failed", "detail": str(exc)}
            continue

        if not data.twenty_enabled:
            logger.debug(f"Twenty node '{data.name}' is disabled, skipping")
            continue

        if render_context is None:
            render_context = build_render_context(context)

        try:
            results[result_key] = await _sync_node(data, render_context, context)
        except Exception as exc:
            logger.error(f"Twenty sync failed for node '{data.name}': {exc}")
            results[result_key] = {"error": str(exc)}

    return results


async def _sync_node(
    data: TwentyNodeData,
    render_context: dict[str, Any],
    context: IntegrationCompletionContext,
) -> dict[str, Any]:
    record_id = resolve_record_id(render_context, data.record_id_path)
    if not record_id:
        logger.warning(
            f"Twenty node '{data.name}': no record id at '{data.record_id_path}', "
            "skipping"
        )
        return {"skipped": True, "reason": "missing_record_id"}

    object_name = resolve_object_name(
        render_context, data.object_name, data.object_path
    )
    if not object_name:
        return {"skipped": True, "reason": "missing_object_name"}

    client = await _build_client(data, context.organization_id)

    result: dict[str, Any] = {
        "object": object_name,
        "record_id": record_id,
        "synced_at": datetime.now(UTC).isoformat(),
    }

    if data.update_record:
        fields = render_fields(
            data.field_mapping, render_context, data.field_types
        )
        if fields:
            await client.update_record(object_name, record_id, fields)
            result["updated_fields"] = sorted(fields.keys())
        else:
            result["updated_fields"] = []
            logger.info(
                f"Twenty node '{data.name}': field mapping rendered empty, "
                "skipping record update"
            )

    if data.create_note:
        result["note"] = await _create_note(client, data, render_context, object_name, record_id)

    return result


async def _build_client(
    data: TwentyNodeData,
    organization_id: int,
) -> TwentyClient:
    if not data.credential_uuid:
        raise ValueError("Twenty node is missing credential_uuid")

    credential = await db_client.get_credential_by_uuid(
        data.credential_uuid, organization_id
    )
    if not credential:
        raise ValueError(f"Twenty credential {data.credential_uuid} not found")

    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    headers.update(build_auth_header(credential))

    return TwentyClient(
        TwentyClientConfig(base_url=data.base_url or "", headers=headers)
    )


async def _create_note(
    client: TwentyClient,
    data: TwentyNodeData,
    render_context: dict[str, Any],
    object_name: str,
    record_id: str,
) -> dict[str, Any]:
    from api.utils.template_renderer import render_template

    title = render_template(data.note_title_template or "AI Call Summary", render_context)
    body = render_template(data.note_body_template or "", render_context)

    payload: dict[str, Any] = {"title": title}
    if body:
        payload[data.note_body_field] = body

    note_id = await client.create_note(payload)
    if not note_id:
        return {"created": False, "reason": "no_note_id_returned"}

    try:
        await client.link_note(note_id, object_name, record_id)
        return {"created": True, "note_id": note_id, "linked": True}
    except Exception as exc:
        logger.warning(f"Twenty note {note_id} created but link failed: {exc}")
        return {"created": True, "note_id": note_id, "linked": False}
