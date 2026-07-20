"""DB client mixin for persisting switchboard call logs."""

from __future__ import annotations

from typing import Any, Optional

from loguru import logger
from sqlalchemy.future import select

from api.db.base_client import BaseDBClient
from api.db.models import SwitchboardCallLogModel


class SwitchboardCallLogClient(BaseDBClient):
    """Mixin providing persistence operations for switchboard call logs."""

    async def create_switchboard_call_log(
        self,
        workflow_run_id: int,
        organization_id: int,
        ledger: dict[str, Any],
        end_reason: Optional[str] = None,
    ) -> SwitchboardCallLogModel:
        """Persist a CallStateLedger snapshot at call-end.

        Args:
            workflow_run_id: The workflow run that just finished.
            organization_id: The owning organization.
            ledger: Full ledger dict (CallStateLedger.model_dump()).
            end_reason: Why the call ended (pipeline_finished / user_hangup / pipeline_error).

        Returns:
            The created SwitchboardCallLogModel row.
        """
        async with self.async_session() as session:
            log_entry = SwitchboardCallLogModel(
                workflow_run_id=workflow_run_id,
                organization_id=organization_id,
                ledger=ledger,
                caller_name=ledger.get("caller_name"),
                intent=ledger.get("intent"),
                disposition=ledger.get("mapped_call_disposition")
                or ledger.get("call_disposition"),
                after_hours=bool(ledger.get("after_hours", False)),
                end_reason=end_reason,
            )
            session.add(log_entry)
            await session.commit()
            await session.refresh(log_entry)
            logger.info(
                "Persisted switchboard call log for run {} (intent={}, disposition={})",
                workflow_run_id,
                log_entry.intent,
                log_entry.disposition,
            )
            return log_entry

    async def get_switchboard_call_log_by_run_id(
        self, workflow_run_id: int
    ) -> Optional[SwitchboardCallLogModel]:
        """Fetch a call log by its workflow run ID."""
        async with self.async_session() as session:
            result = await session.execute(
                select(SwitchboardCallLogModel).where(
                    SwitchboardCallLogModel.workflow_run_id == workflow_run_id
                )
            )
            return result.scalars().first()
