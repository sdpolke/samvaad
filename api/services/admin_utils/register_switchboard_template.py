"""Admin/seed entry point: register the SpinSci switchboard workflow template.

Run once per deployment (Design "Registration (admin/seed, run once per
deployment)") so the switchboard graph produced by
``build_switchboard_graph()`` is available as a workflow-template catalog
entry that the create-agent flow can list and instantiate.

Usage (matches the repo's diagnostics/one-off-script convention, sourcing
the dev environment):

    source venv/bin/activate && set -a && source api/.env && set +a && \\
        python -m api.services.admin_utils.register_switchboard_template

Requirements: 1.3, 1.4.
"""

from __future__ import annotations

import asyncio
import sys

from loguru import logger

from api.services.switchboard.enablement.registrar import (
    SwitchboardTemplateInvalid,
    register_switchboard_template,
)


async def main() -> None:
    """Register (create-or-update) the switchboard workflow template.

    Delegates to ``register_switchboard_template()`` using the default,
    real ``WorkflowTemplateClient``. Logs the outcome via loguru. If the
    assembled switchboard graph fails validation, logs the validation
    errors and re-raises so the operator running this script sees a
    failure (Req 1.6 abort-on-invalid behavior surfaced here as a hard
    failure rather than a silent no-op).
    """
    logger.info("Registering switchboard workflow template...")

    try:
        template = await register_switchboard_template()
    except SwitchboardTemplateInvalid as exc:
        logger.error(
            "Switchboard template registration aborted: invalid graph. Errors: {}",
            exc.errors,
        )
        raise

    logger.info(
        "Switchboard workflow template registered: id={} template_name={}",
        template.id,
        template.template_name,
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except SwitchboardTemplateInvalid:
        sys.exit(1)
    except Exception:
        logger.exception("Switchboard template registration failed unexpectedly")
        sys.exit(1)
