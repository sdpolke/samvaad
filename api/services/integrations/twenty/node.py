from __future__ import annotations

from typing import Any

from pydantic import model_validator

from api.services.integrations.base import IntegrationNodeRegistration
from api.services.workflow.node_data import BaseNodeData
from api.services.workflow.node_specs._base import (
    GraphConstraints,
    NodeCategory,
    NodeExample,
    PropertyType,
)
from api.services.workflow.node_specs.model_spec import (
    build_spec,
    node_spec,
    spec_field,
)

DEFAULT_RECORD_ID_PATH = "initial_context.twenty_record_id"
DEFAULT_OBJECT_PATH = "initial_context.twenty_object"


@node_spec(
    name="twenty",
    display_name="Twenty CRM Sync",
    description="Update a Twenty CRM record with the call outcome after completion",
    llm_hint=(
        "Twenty CRM Sync is a post-call write-back node. It pushes the call "
        "outcome into Twenty over REST and does not participate in the "
        "conversation graph, so it should not be connected to other nodes."
    ),
    category=NodeCategory.integration,
    icon="Building2",
    examples=[
        NodeExample(
            name="twenty_sync",
            data={
                "name": "Update Opportunity",
                "twenty_enabled": True,
                "base_url": "https://crm.example.com",
                "credential_uuid": "11111111-2222-3333-4444-555555555555",
                "object_name": "opportunities",
                "field_mapping": {
                    "stage": "{{gathered_context.opportunity_stage}}",
                    "lastCallDisposition": "{{outcome.disposition}}",
                },
                "create_note": True,
                "note_title_template": "AI Call - {{outcome.disposition}}",
                "note_body_template": (
                    "Disposition: {{outcome.disposition}}\\n"
                    "Recording: {{outcome.recording_url}}"
                ),
            },
        )
    ],
    graph_constraints=GraphConstraints(
        min_incoming=0,
        max_incoming=0,
        min_outgoing=0,
        max_outgoing=0,
    ),
    property_order=(
        "name",
        "twenty_enabled",
        "base_url",
        "credential_uuid",
        "object_name",
        "object_path",
        "record_id_path",
        "update_record",
        "field_mapping",
        "field_types",
        "create_note",
        "note_title_template",
        "note_body_template",
        "note_body_field",
    ),
    field_overrides={
        "name": {
            "spec_default": "Twenty CRM Sync",
            "description": "Short identifier for this Twenty sync configuration.",
        },
        "twenty_enabled": {
            "display_name": "Enabled",
            "description": "When false, Dograh skips writing this call back to Twenty.",
        },
    },
)
class TwentyNodeData(BaseNodeData):
    twenty_enabled: bool = spec_field(
        default=True,
        ui_type=PropertyType.boolean,
        display_name="Enabled",
        description="When false, Dograh skips writing this call back to Twenty.",
    )
    base_url: str | None = spec_field(
        default=None,
        ui_type=PropertyType.string,
        display_name="Twenty Base URL",
        description="Base URL of your Twenty instance, e.g. https://crm.example.com.",
    )
    credential_uuid: str | None = spec_field(
        default=None,
        ui_type=PropertyType.string,
        display_name="Twenty Credential",
        description=(
            "UUID of the stored Twenty API credential used to authenticate REST "
            "calls (an api_key or bearer_token credential)."
        ),
    )
    object_name: str | None = spec_field(
        default=None,
        ui_type=PropertyType.string,
        display_name="Object Collection",
        description=(
            "Twenty REST collection to update, e.g. 'opportunities' or 'people'. "
            "Leave blank to derive it from the call context (object_path)."
        ),
    )
    object_path: str = spec_field(
        default=DEFAULT_OBJECT_PATH,
        ui_type=PropertyType.string,
        display_name="Object Context Path",
        description=(
            "Dotted path used to derive the object name from the call context "
            "when Object Collection is blank."
        ),
    )
    record_id_path: str = spec_field(
        default=DEFAULT_RECORD_ID_PATH,
        ui_type=PropertyType.string,
        display_name="Record ID Path",
        description=(
            "Dotted path to the Twenty record id within the call context "
            "(populated by the Twenty campaign source)."
        ),
    )
    update_record: bool = spec_field(
        default=True,
        ui_type=PropertyType.boolean,
        display_name="Update Record",
        description="When true, PATCH the Twenty record using the field mapping.",
    )
    field_mapping: dict[str, Any] = spec_field(
        default_factory=dict,
        ui_type=PropertyType.json,
        display_name="Field Mapping",
        description=(
            "Map of Twenty field name to a template rendered against the call "
            "context, e.g. {\"stage\": \"{{gathered_context.opportunity_stage}}\"}."
        ),
    )
    field_types: dict[str, Any] = spec_field(
        default_factory=dict,
        ui_type=PropertyType.json,
        display_name="Field Types",
        description=(
            "Optional map of Twenty field name to its type for coercion: "
            "'string', 'number', 'integer', 'boolean', or 'json'. Fields not "
            "listed keep their native type (single-placeholder mappings) or "
            "render as strings."
        ),
    )
    create_note: bool = spec_field(
        default=False,
        ui_type=PropertyType.boolean,
        display_name="Create Note",
        description="When true, create a Twenty note and attach it to the record.",
    )
    note_title_template: str | None = spec_field(
        default=None,
        ui_type=PropertyType.string,
        display_name="Note Title Template",
        description="Template for the note title when Create Note is enabled.",
    )
    note_body_template: str | None = spec_field(
        default=None,
        ui_type=PropertyType.string,
        display_name="Note Body Template",
        description="Template for the note body when Create Note is enabled.",
    )
    note_body_field: str = spec_field(
        default="body",
        ui_type=PropertyType.string,
        display_name="Note Body Field",
        description=(
            "Name of the Twenty note body field to populate (defaults to 'body')."
        ),
    )

    @model_validator(mode="after")
    def _validate_enabled_config(self):
        if not self.twenty_enabled:
            return self

        missing: list[str] = []
        if not self.base_url or not self.base_url.strip():
            missing.append("base_url")
        if not self.credential_uuid or not self.credential_uuid.strip():
            missing.append("credential_uuid")

        if missing:
            fields = ", ".join(missing)
            raise ValueError(
                f"Twenty node is enabled but missing required fields: {fields}"
            )

        if self.update_record and not self.field_mapping and not self.create_note:
            raise ValueError(
                "Twenty node must define a field_mapping or enable create_note"
            )

        return self


SPEC = build_spec(TwentyNodeData)


NODE = IntegrationNodeRegistration(
    type_name="twenty",
    data_model=TwentyNodeData,
    node_spec=SPEC,
)
