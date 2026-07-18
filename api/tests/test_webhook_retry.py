"""Tests for webhook node retry behavior in post-call integrations."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from api.services.workflow.dto import WebhookNodeData
from api.tasks.run_integrations import _execute_webhook_node


@pytest.mark.asyncio
async def test_execute_webhook_node_retries_on_failure():
    webhook_data = WebhookNodeData(
        name="Retry Webhook",
        enabled=True,
        http_method="POST",
        endpoint_url="https://example.com/hook",
        payload_template={"run_id": "{{workflow_run_id}}"},
        retry_enabled=True,
        retry_max_attempts=3,
        retry_backoff_seconds=0.01,
    )

    response = MagicMock()
    response.status_code = 503
    response.text = "unavailable"
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "error",
        request=MagicMock(),
        response=response,
    )

    mock_client = MagicMock()
    mock_client.request = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("api.tasks.run_integrations.httpx.AsyncClient", return_value=mock_client):
        success = await _execute_webhook_node(
            webhook_data=webhook_data,
            render_context={"workflow_run_id": 1},
            organization_id=1,
        )

    assert success is False
    assert mock_client.request.await_count == 3
