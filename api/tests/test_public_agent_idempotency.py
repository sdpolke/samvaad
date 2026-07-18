"""Tests for public agent trigger idempotency and contract helpers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.routes.public_agent import (
    INTEGRATION_CONTRACT_VERSION,
    TriggerCallRequest,
    TriggerCallResponse,
    _resolve_idempotency_key,
)


def test_resolve_idempotency_key_prefers_header():
    request = TriggerCallRequest(
        phone_number="+15555550100",
        idempotency_key="body-key",
    )
    assert _resolve_idempotency_key(request, "header-key") == "header-key"


def test_resolve_idempotency_key_falls_back_to_body():
    request = TriggerCallRequest(
        phone_number="+15555550100",
        idempotency_key="body-key",
    )
    assert _resolve_idempotency_key(request, None) == "body-key"


def test_resolve_idempotency_key_returns_none_when_missing():
    request = TriggerCallRequest(phone_number="+15555550100")
    assert _resolve_idempotency_key(request, None) is None


def test_resolve_idempotency_key_rejects_overlong_header():
    request = TriggerCallRequest(phone_number="+15555550100")
    with pytest.raises(HTTPException) as exc_info:
        _resolve_idempotency_key(request, "x" * 256)
    assert exc_info.value.status_code == 400


def test_trigger_call_response_includes_contract_version():
    response = TriggerCallResponse(
        status="initiated",
        workflow_run_id=1,
        workflow_run_name="WR-API-1234",
    )
    assert response.integration_contract_version == INTEGRATION_CONTRACT_VERSION
    assert response.idempotent_replay is False


@pytest.mark.asyncio
async def test_initiate_call_returns_duplicate_on_idempotent_replay():
    from api.routes import public_agent

    request = TriggerCallRequest(phone_number="+15555550100")
    mock_api_key = MagicMock()
    mock_api_key.organization_id = 10
    mock_api_key.created_by = 1

    mock_trigger = MagicMock()
    mock_trigger.organization_id = 10
    mock_trigger.workflow_id = 99
    mock_trigger.state = "active"

    mock_run = MagicMock()
    mock_run.name = "WR-API-9999"

    with (
        patch.object(
            public_agent.db_client,
            "validate_api_key",
            AsyncMock(return_value=mock_api_key),
        ),
        patch.object(
            public_agent.db_client,
            "get_agent_trigger_by_path",
            AsyncMock(return_value=mock_trigger),
        ),
        patch.object(
            public_agent.db_client,
            "get_idempotent_workflow_run_id",
            AsyncMock(return_value=42),
        ),
        patch.object(
            public_agent.db_client,
            "get_workflow_run_by_id",
            AsyncMock(return_value=mock_run),
        ),
    ):
        response = await public_agent._initiate_call(
            "trigger-uuid",
            request,
            "api-key",
            use_draft=False,
            idempotency_key="person:abc:evt-1",
        )

    assert response.status == "duplicate"
    assert response.workflow_run_id == 42
    assert response.idempotent_replay is True


@pytest.mark.asyncio
async def test_webhook_node_retry_fields_default_disabled():
    from api.services.workflow.dto import WebhookNodeData

    data = WebhookNodeData(name="Test")
    assert data.retry_enabled is False
    assert data.retry_max_attempts == 3
    assert data.retry_backoff_seconds == 2.0
