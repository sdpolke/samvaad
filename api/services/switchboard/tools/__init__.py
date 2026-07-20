"""SpinSci switchboard backend connector tools (Requirement 16).

This subpackage implements the 11 backend connector tools from the design's
"Backend connector tools — input/output contracts" table as workflow tools:

* :mod:`.base` — the :class:`~api.services.switchboard.tools.base.ConnectorTool`
  abstraction, cluster scoping (:class:`~api.services.switchboard.tools.base.ToolCluster`),
  and the deferred SpinSci credential/endpoint + field-mapping seam
  (:class:`~api.services.switchboard.tools.base.ConnectorBinding`, Req 16.2);
* :mod:`.contracts` — the switchboard-side input/output Pydantic contracts;
* :mod:`.backends` — the PoC mock backends (incl. the ``transfer``/``hangup``
  telephony seam wired in task 15.2); and
* :mod:`.registry` — the concrete 11 tools plus registry accessors used by the
  graph builder to scope tools per cluster via ``tool_uuids``.

The tools bind to a credential/endpoint + field mapping and never hardcode
SpinSci wire formats, so the PoC is ready to bind once contracts arrive
(Req 16.1, 16.2).
"""

from __future__ import annotations

from api.services.switchboard.tools.base import (
    ConnectorBinding,
    ConnectorTool,
    SwitchboardCallContext,
    ToolCluster,
)
from api.services.switchboard.tools.registry import (
    CONNECTOR_TOOLS,
    get_connector_tool,
    get_connector_tools,
    tools_for_cluster,
)

__all__ = [
    "ConnectorBinding",
    "ConnectorTool",
    "SwitchboardCallContext",
    "ToolCluster",
    "CONNECTOR_TOOLS",
    "get_connector_tool",
    "get_connector_tools",
    "tools_for_cluster",
]
