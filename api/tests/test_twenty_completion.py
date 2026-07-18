from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.services.integrations.base import IntegrationCompletionContext
from api.services.integrations.twenty.client import TwentyClient, TwentyClientConfig, _pluralize
from api.services.integrations.twenty.completion import run_completion
from api.services.integrations.twenty.mapping import (
    _coerce,
    build_render_context,
    render_fields,
    resolve_object_name,
    resolve_record_id,
)
from api.services.integrations.twenty.node import TwentyNodeData


def _workflow_run(**overrides):
    base = dict(
        id=77,
        campaign_id=5,
        initial_context={"twenty_record_id": "opp-1", "twenty_object": "opportunity"},
        gathered_context={"call_disposition": "interested", "opportunity_stage": "MEETING"},
        usage_info={"call_duration_seconds": 42},
        annotations={},
        recording_url="s3://bucket/rec.wav",
        transcript_url="s3://bucket/t.txt",
        created_at=datetime(2026, 5, 29, tzinfo=UTC),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _ctx(workflow_run, public_token=None):
    return IntegrationCompletionContext(
        workflow_run_id=workflow_run.id,
        workflow_run=workflow_run,
        workflow_definition={},
        definition_id=1,
        organization_id=9,
        public_token=public_token,
    )


def test_node_requires_config_when_enabled():
    with pytest.raises(ValueError):
        TwentyNodeData.model_validate({"name": "x", "twenty_enabled": True})


def test_node_disabled_skips_validation():
    data = TwentyNodeData.model_validate({"name": "x", "twenty_enabled": False})
    assert data.twenty_enabled is False


def test_pluralize_handles_twenty_objects():
    assert _pluralize("person") == "people"
    assert _pluralize("company") == "companies"
    assert _pluralize("opportunity") == "opportunities"
    assert _pluralize("opportunities") == "opportunities"


def test_build_render_context_exposes_outcome():
    ctx = _ctx(_workflow_run())
    rendered = build_render_context(ctx)
    assert rendered["outcome"]["disposition"] == "interested"
    assert rendered["outcome"]["duration_seconds"] == 42
    assert rendered["recording_url"] == "s3://bucket/rec.wav"


def test_render_context_uses_public_token_urls():
    ctx = _ctx(_workflow_run(), public_token="tok123")
    rendered = build_render_context(ctx)
    assert rendered["recording_url"].endswith("/workflow/tok123/recording")
    assert rendered["transcript_url"].endswith("/workflow/tok123/transcript")


def test_resolve_record_id_and_object_name():
    rendered = build_render_context(_ctx(_workflow_run()))
    assert resolve_record_id(rendered, "initial_context.twenty_record_id") == "opp-1"
    assert resolve_object_name(rendered, None, "initial_context.twenty_object") == "opportunity"
    assert resolve_object_name(rendered, "people", "initial_context.twenty_object") == "people"


def test_render_fields_drops_empty():
    rendered = build_render_context(_ctx(_workflow_run()))
    fields = render_fields(
        {
            "stage": "{{gathered_context.opportunity_stage}}",
            "disposition": "{{outcome.disposition}}",
            "missing": "{{gathered_context.does_not_exist}}",
        },
        rendered,
    )
    assert fields == {"stage": "MEETING", "disposition": "interested"}


def test_render_fields_preserves_native_type_for_single_placeholder():
    rendered = build_render_context(_ctx(_workflow_run()))
    fields = render_fields({"duration": "{{outcome.duration_seconds}}"}, rendered)
    assert fields["duration"] == 42
    assert isinstance(fields["duration"], int)


def test_render_fields_mixed_template_stays_string():
    rendered = build_render_context(_ctx(_workflow_run()))
    fields = render_fields(
        {"label": "call lasted {{outcome.duration_seconds}}s"}, rendered
    )
    assert fields["label"] == "call lasted 42s"


def test_render_fields_explicit_type_hints():
    run = _workflow_run(
        gathered_context={
            "amount": "1500.50",
            "is_qualified": "yes",
            "count": "3",
        }
    )
    rendered = build_render_context(_ctx(run))
    fields = render_fields(
        {
            "amount": "{{gathered_context.amount}}",
            "qualified": "{{gathered_context.is_qualified}}",
            "count": "{{gathered_context.count}}",
        },
        rendered,
        field_types={
            "amount": "number",
            "qualified": "boolean",
            "count": "integer",
        },
    )
    assert fields == {"amount": 1500.5, "qualified": True, "count": 3}


def test_coerce_json_and_string():
    assert _coerce("meta", '{"a": 1}', "json") == {"a": 1}
    assert _coerce("meta", {"a": 1}, "string") == '{"a": 1}'
    assert _coerce("flag", "off", "boolean") is False


def test_render_fields_bad_coercion_falls_back_to_raw():
    rendered = build_render_context(_ctx(_workflow_run()))
    fields = render_fields(
        {"stage": "{{gathered_context.opportunity_stage}}"},
        rendered,
        field_types={"stage": "integer"},
    )
    assert fields["stage"] == "MEETING"


@pytest.mark.asyncio
async def test_run_completion_updates_record():
    node = {
        "id": "n1",
        "type": "twenty",
        "data": {
            "name": "Update Opportunity",
            "twenty_enabled": True,
            "base_url": "http://localhost:3000",
            "credential_uuid": "cred-1",
            "object_name": "opportunities",
            "field_mapping": {"stage": "{{gathered_context.opportunity_stage}}"},
        },
    }
    ctx = _ctx(_workflow_run())

    credential = SimpleNamespace(
        credential_type="api_key",
        credential_data={"header_name": "Authorization", "api_key": "Bearer t"},
        name="twenty",
    )

    with patch(
        "api.services.integrations.twenty.completion.db_client.get_credential_by_uuid",
        new=AsyncMock(return_value=credential),
    ), patch.object(
        TwentyClient, "update_record", new=AsyncMock(return_value={"data": {}})
    ) as update_mock:
        results = await run_completion([node], ctx)

    update_mock.assert_awaited_once()
    args = update_mock.await_args.args
    assert args[0] == "opportunities"
    assert args[1] == "opp-1"
    assert args[2] == {"stage": "MEETING"}
    assert results["twenty_n1"]["updated_fields"] == ["stage"]


@pytest.mark.asyncio
async def test_run_completion_skips_without_record_id():
    node = {
        "id": "n2",
        "type": "twenty",
        "data": {
            "name": "Update Opportunity",
            "twenty_enabled": True,
            "base_url": "http://localhost:3000",
            "credential_uuid": "cred-1",
            "object_name": "opportunities",
            "field_mapping": {"stage": "{{gathered_context.opportunity_stage}}"},
        },
    }
    run = _workflow_run(initial_context={})
    results = await run_completion([node], _ctx(run))
    assert results["twenty_n2"]["skipped"] is True
    assert results["twenty_n2"]["reason"] == "missing_record_id"


@pytest.mark.asyncio
async def test_run_completion_skips_disabled_node():
    node = {"id": "n3", "type": "twenty", "data": {"name": "x", "twenty_enabled": False}}
    results = await run_completion([node], _ctx(_workflow_run()))
    assert results == {}
