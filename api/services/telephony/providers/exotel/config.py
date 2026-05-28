"""Pydantic request/response models for Exotel telephony configuration."""

from pydantic import BaseModel, field_validator


class ExotelConfigRequest(BaseModel):
    """Incoming request model for saving Exotel credentials."""

    api_key: str
    api_token: str
    account_sid: str
    subdomain: str = "api.in.exotel.com"
    app_id: str

    @field_validator("account_sid", "api_key", "api_token", "app_id")
    @classmethod
    def must_be_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field must be a non-empty string")
        return v.strip()


class ExotelConfigResponse(BaseModel):
    """Outgoing response model (masks sensitive fields)."""

    account_sid: str
    subdomain: str
    app_id: str
