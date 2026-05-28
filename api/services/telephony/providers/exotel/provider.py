"""Exotel telephony provider implementation."""

from typing import Any, Dict, List, Optional

import httpx
from loguru import logger

from api.services.telephony.base import (
    CallInitiationResult,
    NormalizedInboundData,
    ProviderSyncResult,
    TelephonyProvider,
)


class ExotelProvider(TelephonyProvider):
    """Exotel telephony provider for Indian cloud telephony."""

    PROVIDER_NAME = "exotel"
    WEBHOOK_ENDPOINT = "exotel/webhook"

    def __init__(self, config: Dict[str, Any]):
        self._api_key = config.get("api_key", "")
        self._api_token = config.get("api_token", "")
        self._account_sid = config.get("account_sid", "")
        self._subdomain = config.get("subdomain", "api.in.exotel.com")
        self._app_id = config.get("app_id", "")
        self._from_numbers = config.get("from_numbers", [])
        self._base_url = (
            f"https://{self._subdomain}/v1/Accounts/{self._account_sid}"
        )

    @property
    def from_numbers(self) -> List[str]:
        return self._from_numbers

    async def initiate_call(
        self,
        to_number: str,
        webhook_url: str,
        workflow_run_id: Optional[int] = None,
        from_number: Optional[str] = None,
        **kwargs: Any,
    ) -> CallInitiationResult:
        """Initiate an outbound call via Exotel Connect to Flow API."""
        caller_id = from_number or (self._from_numbers[0] if self._from_numbers else self._app_id)

        # Build custom field with workflow metadata
        custom_field = ""
        if workflow_run_id:
            custom_field = f"workflow_run_id={workflow_run_id}"

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}/Calls/connect.json",
                auth=(self._api_key, self._api_token),
                data={
                    "From": caller_id,
                    "To": to_number,
                    "CallerId": caller_id,
                    "Url": f"http://my.exotel.com/exoml/start_voice/{self._app_id}",
                    "StatusCallback": webhook_url,
                    "CustomField": custom_field,
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()

        call_data = data.get("Call", data)
        call_sid = call_data.get("Sid", "unknown")

        logger.info(f"Exotel call initiated: {call_sid} → {to_number}")

        return CallInitiationResult(
            call_id=call_sid,
            status=call_data.get("Status", "queued"),
            caller_number=caller_id,
            provider_metadata={"exotel_call_sid": call_sid},
            raw_response=data,
        )

    async def get_call_status(self, call_id: str) -> Dict[str, Any]:
        """Get call status from Exotel API."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/Calls/{call_id}.json",
                auth=(self._api_key, self._api_token),
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_available_phone_numbers(self) -> List[str]:
        """Return configured phone numbers."""
        return self._from_numbers

    def validate_config(self) -> bool:
        """Validate Exotel configuration."""
        return bool(
            self._api_key
            and self._api_token
            and self._account_sid
            and self._app_id
        )

    async def verify_webhook_signature(
        self, url: str, params: Dict[str, Any], signature: str
    ) -> bool:
        """Exotel does not provide webhook signature verification."""
        return True

    async def get_webhook_response(
        self, workflow_id: int, user_id: int, workflow_run_id: int
    ) -> str:
        """Generate Exotel response for stream initiation.

        Exotel uses its Voicebot applet for WebSocket streaming,
        so the webhook response is typically handled by the applet config.
        """
        return ""

    async def get_call_cost(self, call_id: str) -> Dict[str, Any]:
        """Get call cost from Exotel."""
        try:
            status = await self.get_call_status(call_id)
            call_data = status.get("Call", status)
            return {
                "cost_usd": 0.0,  # Exotel bills in INR, conversion needed
                "duration": int(call_data.get("Duration", 0)),
                "status": call_data.get("Status", "unknown"),
                "raw_response": status,
            }
        except Exception as e:
            logger.warning(f"Failed to get Exotel call cost for {call_id}: {e}")
            return {"cost_usd": 0.0, "duration": 0, "status": "unknown"}

    def parse_status_callback(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Exotel status callback into standardized format."""
        # Exotel status mapping
        status_map = {
            "completed": "completed",
            "busy": "busy",
            "no-answer": "no-answer",
            "failed": "failed",
            "canceled": "cancelled",
            "ringing": "ringing",
            "in-progress": "in-progress",
        }

        raw_status = data.get("Status", data.get("CallStatus", "")).lower()
        normalized_status = status_map.get(raw_status, raw_status)

        return {
            "call_id": data.get("CallSid", data.get("Sid", "")),
            "status": normalized_status,
            "from_number": data.get("From", ""),
            "to_number": data.get("To", ""),
            "duration": data.get("Duration", data.get("RecordingDuration")),
            "extra": {
                "direction": data.get("Direction", ""),
                "start_time": data.get("StartTime", ""),
                "end_time": data.get("EndTime", ""),
            },
        }

    async def handle_websocket(
        self, websocket, workflow_id: int, user_id: int, workflow_run_id: int
    ) -> None:
        """Handle Exotel WebSocket connection.

        The actual WebSocket handling is done by the transport factory
        via run_pipeline_telephony. This method is a fallback.
        """
        raise NotImplementedError(
            "Exotel WebSocket handling is done via the transport factory"
        )

    @classmethod
    def can_handle_webhook(
        cls, webhook_data: Dict[str, Any], headers: Dict[str, str]
    ) -> bool:
        """Detect Exotel webhooks by checking for Exotel-specific fields."""
        # Exotel sends CallSid and uses specific field naming
        return "CallSid" in webhook_data and "EventType" in webhook_data

    @staticmethod
    def parse_inbound_webhook(webhook_data: Dict[str, Any]) -> NormalizedInboundData:
        """Parse Exotel inbound webhook data."""
        return NormalizedInboundData(
            provider="exotel",
            call_id=webhook_data.get("CallSid", ""),
            from_number=webhook_data.get("From", ""),
            to_number=webhook_data.get("To", ""),
            direction="inbound",
            call_status=webhook_data.get("Status", "ringing"),
            account_id=webhook_data.get("AccountSid", ""),
            raw_data=webhook_data,
        )

    @staticmethod
    def validate_account_id(config_data: dict, webhook_account_id: str) -> bool:
        """Validate Exotel account SID matches."""
        return config_data.get("account_sid") == webhook_account_id

    async def verify_inbound_signature(
        self, url: str, webhook_data: Dict[str, Any], headers: Dict[str, str], body: str = ""
    ) -> bool:
        """Exotel does not provide inbound webhook signature verification."""
        return True

    async def start_inbound_stream(
        self,
        *,
        websocket_url: str,
        workflow_run_id: int,
        normalized_data: "NormalizedInboundData",
        backend_endpoint: str,
    ) -> Any:
        """Exotel inbound streams are handled by the Voicebot applet configuration.

        The applet is pre-configured to connect to the WebSocket URL.
        """
        return {"status": "ok", "message": "Exotel inbound handled by applet"}

    @staticmethod
    def generate_error_response(error_type: str, message: str) -> tuple:
        """Generate error response for Exotel."""
        from fastapi.responses import JSONResponse

        return JSONResponse(
            content={"error": error_type, "message": message},
            status_code=400,
        ), "application/json"

    async def transfer_call(
        self,
        destination: str,
        transfer_id: str,
        conference_name: str,
        timeout: int = 30,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Transfer call via Exotel."""
        # Exotel supports call transfer via their API
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}/Calls/connect.json",
                auth=(self._api_key, self._api_token),
                data={
                    "From": kwargs.get("from_number", self._app_id),
                    "To": destination,
                    "CallerId": kwargs.get("caller_id", self._app_id),
                },
                timeout=float(timeout),
            )
            data = resp.json()

        return {
            "call_sid": data.get("Call", {}).get("Sid", ""),
            "status": "initiated",
            "provider": "exotel",
        }

    def supports_transfers(self) -> bool:
        """Exotel supports call transfers."""
        return True
