"""Core abstractions for the SpinSci switchboard backend connector tools (Req 16).

Each switchboard *capability* (Req 16.1) — patient lookup, directory lookup, the
FAQ knowledge base, DOB validation, identity verification, the routing chain,
transfer, hangup, and the scheduling handoff/engine — is modelled here as a
:class:`ConnectorTool`. A connector tool bundles three things:

* a **switchboard-side input/output contract** (two Pydantic models describing the
  shapes the switchboard sends/receives — the design.md "Backend connector tools —
  input/output contracts" table), so callers never depend on SpinSci's wire
  schema;
* a **backend** callable that actually services a request — for the PoC these are
  the deterministic mock backends in :mod:`.backends`; and
* a **binding** (:class:`ConnectorBinding`) that points at a credential + endpoint
  and a field mapping. This is the deferred SpinSci seam (Req 16.2): tools bind to
  a credential/endpoint and map field names, and must **not** hardcode SpinSci's
  wire formats. The binding is empty until SpinSci delivers contracts, so the PoC
  runs against mocks with no wire assumptions baked in.

Tools are exposed to the workflow engine through :meth:`ConnectorTool.to_function_schema`
(the LLM function-calling schema) and :meth:`ConnectorTool.to_tool_definition`
(a ``ToolModel``-style ``definition`` payload). Because every tool carries the
:class:`ToolCluster` set it is scoped to, the graph builder (task 16.8) can attach
each one to only the nodes of its cluster via ``tool_uuids`` — so, e.g.,
``transfer``/``route_metadata_resolution`` exist only on Routing nodes and cannot
fire earlier.

This module is pure and side-effect-free (no network, no DB, no telephony); the
mock backends live alongside in :mod:`.backends` and the concrete tool set in
:mod:`.registry`.

Design references:
- ``design.md`` → "Backend connector tools — input/output contracts"
- ``requirements.md`` → Requirement 16 (16.1 capabilities, 16.2 externalized wire
  contracts / credential + field-mapping binding)

Requirements: 16.1, 16.2.
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    Awaitable,
    Callable,
    Generic,
    Mapping,
    Optional,
    Protocol,
    Type,
    TypeVar,
    runtime_checkable,
)

from loguru import logger
from pydantic import BaseModel

from api.enums import ToolCategory

TInput = TypeVar("TInput", bound=BaseModel)
TOutput = TypeVar("TOutput", bound=BaseModel)

#: Default per-request timeout applied to the (future) HTTP binding, in ms. The
#: mock backends ignore it; it is surfaced on :meth:`ConnectorTool.to_tool_definition`
#: so a real binding has a sane default when SpinSci contracts arrive.
DEFAULT_TOOL_TIMEOUT_MS: int = 5000


class ToolCluster(str, Enum):
    """The switchboard node clusters a connector tool may be scoped to.

    Mirrors the "Scoped to" column of the design's connector-tool table. Per-node
    tool scoping is the switchboard's structural gate mechanism (Req 1.7, 9.2): a
    node can only invoke the tools listed in its ``tool_uuids``, so attaching a
    tool to a cluster restricts *where* the capability can be used. For example
    ``transfer`` and ``route_metadata_resolution`` are scoped to
    :attr:`ROUTING` only, so no transfer or destination resolution can occur before
    the Routing phase.
    """

    GREETING = "greeting"
    BUSINESS_HOURS = "business_hours"
    AFTER_HOURS = "after_hours"
    AUTHENTICATION = "authentication"
    ROUTING = "routing"
    SCHEDULING = "scheduling"


@dataclass(frozen=True)
class ConnectorBinding:
    """The deferred SpinSci wire-contract seam for a connector tool (Req 16.2).

    A binding declares *how* a tool reaches its backend without encoding SpinSci's
    internal wire format anywhere in switchboard code:

    * :attr:`credential_key` — the name/UUID of the credential the tool
      authenticates with (resolved through the credentials service at runtime,
      never a hardcoded secret).
    * :attr:`endpoint` — the backend URL the tool calls.
    * :attr:`field_mapping` — a mapping from **switchboard-side** contract field
      names to the backend's field names. When SpinSci supplies their schema, only
      this mapping (plus the endpoint/credential) is filled in — no switchboard
      code changes.

    All three are empty/``None`` for the PoC (:data:`UNBOUND`), so the mock
    backends service every tool and the switchboard makes no assumption about
    SpinSci internals. A binding is intentionally inert data: translating a request
    through :attr:`field_mapping` is the job of a future HTTP backend (task
    post-15.x), not of this dataclass.
    """

    credential_key: Optional[str] = None
    endpoint: Optional[str] = None
    field_mapping: Mapping[str, str] = field(default_factory=dict)

    @property
    def is_bound(self) -> bool:
        """Whether a real backend endpoint has been configured for this tool."""
        return bool(self.endpoint)

    def map_field(self, switchboard_field: str) -> str:
        """Translate a switchboard-side field name to the backend's field name.

        Returns the mapped backend field name when :attr:`field_mapping` defines
        one, else the original switchboard field name unchanged (identity mapping).
        """
        return self.field_mapping.get(switchboard_field, switchboard_field)


#: The empty binding used until SpinSci delivers wire contracts (Req 16.2). Tools
#: default to this so the PoC runs entirely against mock backends.
UNBOUND: ConnectorBinding = ConnectorBinding()


@dataclass(frozen=True)
class SwitchboardCallContext:
    """Runtime call context threaded to side-effecting connector backends (task 15.2).

    Most connector backends are pure/deterministic and need only the tenant
    ``organization_id`` (passed to :meth:`ConnectorTool.invoke`). The terminal
    telephony backends (``transfer``/``hangup``) additionally need to reach the
    *active* call to resolve the correct telephony provider through the
    registry/factory (never a provider class directly) and address the live
    channel — so the caller (the workflow engine) threads this context in.

    Following least-privilege, this carries only the identifiers required to
    resolve the provider and the active call — the org and the workflow run —
    never credentials or provider handles. The provider is resolved per run via
    ``api.services.telephony.factory.get_telephony_provider_for_run``, which is
    org-scoped and therefore enforces tenant isolation on the resolved config.
    """

    organization_id: int
    workflow_run_id: int


@runtime_checkable
class ConnectorBackend(Protocol[TInput, TOutput]):
    """The async backend that services a connector tool's validated request.

    A backend receives the parsed switchboard-side *input* model and returns the
    switchboard-side *output* model. For the PoC these are deterministic mocks
    (:mod:`.backends`); when SpinSci contracts arrive they are replaced by an HTTP
    backend that uses the tool's :class:`ConnectorBinding` to translate fields and
    call the real endpoint — without changing the tool's contract.

    Side-effecting backends (the ``transfer``/``hangup`` telephony seam) may also
    accept a keyword-only ``call_context`` carrying the active-call identifiers
    they need to resolve a telephony provider; pure backends omit it and only
    receive ``organization_id`` (see :meth:`ConnectorTool.invoke`).
    """

    async def __call__(
        self,
        request: TInput,
        *,
        organization_id: Optional[int] = None,
        call_context: Optional[SwitchboardCallContext] = None,
    ) -> TOutput:
        ...


BackendFn = Callable[..., Awaitable[BaseModel]]

# Map contract primitive types to JSON-schema types for the LLM function schema.
_JSON_TYPE_MAP: dict[str, str] = {
    "string": "string",
    "integer": "integer",
    "number": "number",
    "boolean": "boolean",
    "array": "array",
    "object": "object",
}


def slugify_tool_name(name: str) -> str:
    """Normalize a tool name into a safe LLM function name (lowercase + underscores)."""
    slug = re.sub(r"[^a-z0-9_]", "_", name.strip().lower())
    return re.sub(r"_+", "_", slug).strip("_")


class ConnectorTool(Generic[TInput, TOutput]):
    """A switchboard backend connector tool (Req 16.1).

    Binds a switchboard-side input/output contract to a backend and a
    credential/endpoint :class:`ConnectorBinding`, and exposes the tool to the
    workflow engine in a scope-aware way. The tool is deliberately agnostic of
    SpinSci's wire format: it validates against its own contract models and lets
    the binding/backend handle translation (Req 16.2).

    Attributes:
        name: Stable tool key (e.g. ``"patient_lookup"``); also the LLM function
            name after slugification.
        description: Human/LLM-facing description of the capability.
        input_model: Pydantic model for the switchboard-side request.
        output_model: Pydantic model for the switchboard-side response.
        clusters: The :class:`ToolCluster` set this tool is scoped to (drives
            per-node ``tool_uuids`` attachment; Req 1.7, 9.2).
        backend: The async backend servicing the request (a mock for the PoC).
        binding: The credential/endpoint + field-mapping seam (Req 16.2).
        sensitive_fields: Contract field names holding PII/secret values that must
            be masked in logs/config (e.g. DOB, patient identifiers).
    """

    def __init__(
        self,
        *,
        name: str,
        description: str,
        input_model: Type[TInput],
        output_model: Type[TOutput],
        clusters: frozenset[ToolCluster],
        backend: BackendFn,
        binding: ConnectorBinding = UNBOUND,
        sensitive_fields: frozenset[str] = frozenset(),
        timeout_ms: int = DEFAULT_TOOL_TIMEOUT_MS,
    ) -> None:
        if not clusters:
            raise ValueError(f"Connector tool {name!r} must be scoped to ≥1 cluster")
        self.name = name
        self.function_name = slugify_tool_name(name)
        self.description = description
        self.input_model = input_model
        self.output_model = output_model
        self.clusters = clusters
        self._backend = backend
        self.binding = binding
        self.sensitive_fields = sensitive_fields
        self.timeout_ms = timeout_ms

    # -- scoping -----------------------------------------------------------------

    def is_scoped_to(self, cluster: ToolCluster) -> bool:
        """Whether this tool may be attached to nodes of ``cluster`` (Req 1.7)."""
        return cluster in self.clusters

    # -- invocation --------------------------------------------------------------

    async def invoke(
        self,
        inputs: Mapping[str, Any],
        *,
        organization_id: Optional[int] = None,
        call_context: Optional[SwitchboardCallContext] = None,
    ) -> TOutput:
        """Validate ``inputs`` against the contract, run the backend, validate output.

        The request dict is validated into :attr:`input_model` (untrusted input is
        validated at the boundary), handed to the backend, and the backend's result
        is validated into :attr:`output_model` so the switchboard-side contract
        holds on both sides regardless of what the backend (mock or real) returns.

        Args:
            inputs: The switchboard-side request fields.
            organization_id: Tenant/org context threaded to the backend.
            call_context: Optional active-call context (org + workflow run) used by
                the side-effecting telephony backends (``transfer``/``hangup``) to
                resolve a provider via the registry/factory. Forwarded only to
                backends that declare a ``call_context`` parameter, so the pure
                backends keep their ``(request, *, organization_id)`` signature.

        Returns:
            The validated :attr:`output_model` instance.

        Raises:
            pydantic.ValidationError: If ``inputs`` or the backend result do not
                satisfy the contract.
        """
        request = self.input_model.model_validate(dict(inputs))
        logger.debug(
            "Invoking switchboard connector tool {} (bound={})",
            self.name,
            self.binding.is_bound,
        )
        backend_kwargs: dict[str, Any] = {"organization_id": organization_id}
        # Only the side-effecting telephony backends opt into call_context; forward
        # it solely to backends that declare the parameter so the pure mock backends
        # retain their stable (request, *, organization_id) signature.
        try:
            backend_params = inspect.signature(self._backend).parameters
        except (TypeError, ValueError):
            backend_params = {}
        if "call_context" in backend_params:
            backend_kwargs["call_context"] = call_context
        result = await self._backend(request, **backend_kwargs)
        if isinstance(result, self.output_model):
            return result
        return self.output_model.model_validate(
            result.model_dump() if isinstance(result, BaseModel) else result
        )

    # -- engine integration ------------------------------------------------------

    def _parameter_schema(self) -> dict[str, Any]:
        """Derive an OpenAI-style ``parameters`` object from the input model."""
        model_schema = self.input_model.model_json_schema()
        properties = model_schema.get("properties", {})
        required = model_schema.get("required", [])
        return {
            "type": "object",
            "properties": properties,
            "required": list(required),
        }

    def to_function_schema(self) -> dict[str, Any]:
        """Return the LLM function-calling schema for this tool.

        Shaped like the other workflow tools (``{"type": "function", "function":
        {...}}``) so the connector tools plug into the same engine tool surface.
        """
        return {
            "type": "function",
            "function": {
                "name": self.function_name,
                "description": self.description,
                "parameters": self._parameter_schema(),
            },
        }

    def _definition_parameters(self) -> list[dict[str, Any]]:
        """Describe contract inputs as ``ToolModel`` HTTP-tool parameter entries."""
        model_schema = self.input_model.model_json_schema()
        properties = model_schema.get("properties", {})
        required = set(model_schema.get("required", []))
        params: list[dict[str, Any]] = []
        for field_name, field_schema in properties.items():
            json_type = field_schema.get("type", "string")
            params.append(
                {
                    "name": field_name,
                    "type": _JSON_TYPE_MAP.get(json_type, "string"),
                    "description": field_schema.get("description", ""),
                    "required": field_name in required,
                }
            )
        return params

    def to_tool_definition(self) -> dict[str, Any]:
        """Return a ``ToolModel``-style ``definition`` payload for registration.

        Produces the JSON the graph builder persists as a ``ToolModel`` row so the
        tool is registerable and scopable by ``tool_uuids``. The ``config`` carries
        the :class:`ConnectorBinding` (endpoint/credential/field-mapping) rather
        than any SpinSci wire schema, keeping wire contracts external (Req 16.2).
        Until SpinSci binds it, ``url``/``credential_uuid`` are empty and the mock
        backend services calls.
        """
        return {
            "schema_version": 1,
            "type": ToolCategory.HTTP_API.value,
            "config": {
                "url": self.binding.endpoint or "",
                "credential_uuid": self.binding.credential_key,
                "field_mapping": dict(self.binding.field_mapping),
                "parameters": self._definition_parameters(),
                "timeout_ms": self.timeout_ms,
            },
            "switchboard": {
                "clusters": sorted(c.value for c in self.clusters),
                "sensitive_fields": sorted(self.sensitive_fields),
            },
        }


__all__ = [
    "DEFAULT_TOOL_TIMEOUT_MS",
    "ToolCluster",
    "ConnectorBinding",
    "UNBOUND",
    "SwitchboardCallContext",
    "ConnectorBackend",
    "ConnectorTool",
    "slugify_tool_name",
]
