"""Database client for public agent trigger idempotency keys."""

from typing import Optional

from loguru import logger
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from api.db.base_client import BaseDBClient
from api.db.models import ApiTriggerIdempotencyModel


class ApiTriggerIdempotencyClient(BaseDBClient):
    """Client for deduplicating public agent trigger requests."""

    async def get_idempotent_workflow_run_id(
        self,
        organization_id: int,
        idempotency_key: str,
    ) -> Optional[int]:
        """Return an existing workflow run ID for a prior idempotent trigger."""
        async with self.async_session() as session:
            result = await session.execute(
                select(ApiTriggerIdempotencyModel.workflow_run_id).where(
                    ApiTriggerIdempotencyModel.organization_id == organization_id,
                    ApiTriggerIdempotencyModel.idempotency_key == idempotency_key,
                )
            )
            row = result.scalar_one_or_none()
            return row

    async def store_idempotency_key(
        self,
        organization_id: int,
        idempotency_key: str,
        trigger_path: str,
        workflow_run_id: int,
    ) -> bool:
        """Persist an idempotency key after a successful trigger.

        Returns:
            True if the key was stored, False if another request stored it first.
        """
        async with self.async_session() as session:
            try:
                await session.execute(
                    insert(ApiTriggerIdempotencyModel).values(
                        organization_id=organization_id,
                        idempotency_key=idempotency_key,
                        trigger_path=trigger_path,
                        workflow_run_id=workflow_run_id,
                    )
                )
                await session.commit()
                return True
            except IntegrityError:
                await session.rollback()
                logger.info(
                    "Idempotency key collision for org {} key {}",
                    organization_id,
                    idempotency_key,
                )
                return False
