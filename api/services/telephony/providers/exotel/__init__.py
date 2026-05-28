"""Exotel telephony provider package."""

from typing import Any, Dict

from api.services.telephony.registry import (
    ProviderSpec,
    ProviderUIField,
    ProviderUIMetadata,
    register,
)

from .config import ExotelConfigRequest, ExotelConfigResponse
from .provider import ExotelProvider
from .transport import create_transport


def _config_loader(value: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "provider": "exotel",
        "api_key": value.get("api_key"),
        "api_token": value.get("api_token"),
        "account_sid": value.get("account_sid"),
        "subdomain": value.get("subdomain", "api.in.exotel.com"),
        "app_id": value.get("app_id"),
    }


_UI_METADATA = ProviderUIMetadata(
    display_name="Exotel",
    docs_url="https://developer.exotel.com/api/",
    fields=[
        ProviderUIField(
            name="api_key",
            label="API Key",
            type="password",
            sensitive=True,
            description="Exotel API Key",
        ),
        ProviderUIField(
            name="api_token",
            label="API Token",
            type="password",
            sensitive=True,
            description="Exotel API Token",
        ),
        ProviderUIField(
            name="account_sid",
            label="Account SID",
            type="text",
            description="Exotel Account SID (e.g., yourcompany2m)",
        ),
        ProviderUIField(
            name="subdomain",
            label="Subdomain",
            type="text",
            required=False,
            placeholder="api.in.exotel.com",
            description="Exotel API subdomain",
        ),
        ProviderUIField(
            name="app_id",
            label="App ID",
            type="text",
            description="Exotel Voicebot App ID",
        ),
    ],
)


SPEC = ProviderSpec(
    name="exotel",
    provider_cls=ExotelProvider,
    config_loader=_config_loader,
    transport_factory=create_transport,
    transport_sample_rate=8000,
    config_request_cls=ExotelConfigRequest,
    config_response_cls=ExotelConfigResponse,
    account_id_credential_field="account_sid",
    ui_metadata=_UI_METADATA,
)

register(SPEC)

__all__ = [
    "SPEC",
    "ExotelConfigRequest",
    "ExotelConfigResponse",
    "ExotelProvider",
    "create_transport",
]
