"""Callback requests API endpoints.

Provides endpoints for listing and managing callback requests
associated with campaigns.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.db import db_client
from api.db.models import UserModel
from api.services.auth.depends import get_user

router = APIRouter(prefix="/callbacks")


class CallbackRequestResponse(BaseModel):
    id: int
    organization_id: int
    workflow_run_id: Optional[int]
    campaign_id: Optional[int]
    lead_name: Optional[str]
    phone_number: str
    company: Optional[str]
    callback_date: str
    callback_time: str
    timezone: str
    reason: Optional[str]
    status: str
    failure_reason: Optional[str]
    created_at: str


class CallbackListResponse(BaseModel):
    callbacks: List[CallbackRequestResponse]
    total_count: int


@router.get("/campaign/{campaign_id}")
async def list_campaign_callbacks(
    campaign_id: int,
    user: UserModel = Depends(get_user),
) -> CallbackListResponse:
    """List all callback requests for a campaign."""
    # Verify campaign belongs to user's organization
    campaign = await db_client.get_campaign(campaign_id, user.selected_organization_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    callbacks = await db_client.get_callback_requests_by_campaign(campaign_id)

    return CallbackListResponse(
        callbacks=[
            CallbackRequestResponse(
                id=cb.id,
                organization_id=cb.organization_id,
                workflow_run_id=cb.workflow_run_id,
                campaign_id=cb.campaign_id,
                lead_name=cb.lead_name,
                phone_number=cb.phone_number,
                company=cb.company,
                callback_date=cb.callback_date,
                callback_time=cb.callback_time,
                timezone=cb.timezone,
                reason=cb.reason,
                status=cb.status,
                failure_reason=cb.failure_reason,
                created_at=cb.created_at.isoformat() if cb.created_at else "",
            )
            for cb in callbacks
        ],
        total_count=len(callbacks),
    )


@router.post("/{callback_id}/cancel")
async def cancel_callback(
    callback_id: int,
    user: UserModel = Depends(get_user),
):
    """Cancel a pending callback request."""
    callback = await db_client.get_callback_request(callback_id)
    if not callback:
        raise HTTPException(status_code=404, detail="Callback not found")

    # Verify organization ownership
    if callback.organization_id != user.selected_organization_id:
        raise HTTPException(status_code=404, detail="Callback not found")

    if callback.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel callback in '{callback.status}' state",
        )

    await db_client.update_callback_status(callback_id, "cancelled")

    return {"status": "cancelled", "callback_id": callback_id}
