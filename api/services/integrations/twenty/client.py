"""Thin async REST client for Twenty CRM.

Only the verbs needed for post-call updates are implemented:
- ``update_record`` -> PATCH /rest/{object}/{id}
- ``create_note``   -> POST  /rest/notes
- ``link_note``     -> POST  /rest/noteTargets

The client talks to Twenty exclusively over its public REST API so Twenty's
source code never needs to change.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx
from loguru import logger
from pydantic import BaseModel, field_validator


class TwentyClientConfig(BaseModel):
    base_url: str
    headers: dict[str, str]
    timeout_seconds: float = 15.0

    @field_validator("base_url")
    @classmethod
    def _normalize_base_url(cls, value: str) -> str:
        value = (value or "").strip().rstrip("/")
        if not value:
            raise ValueError("base_url must not be empty")
        return value


def _pluralize(object_name: str) -> str:
    """Map a singular Twenty object name to its REST collection name.

    Twenty REST collections are plural (``/rest/opportunities``) while the call
    context stores the singular form (``opportunity``).
    """
    name = (object_name or "").strip().strip("/")
    if not name:
        return name
    if name.endswith("s"):
        return name
    if name == "person":
        return "people"
    if name == "company":
        return "companies"
    if name.endswith("y"):
        return f"{name[:-1]}ies"
    return f"{name}s"


class TwentyClient:
    """Minimal Twenty REST client used by the post-call completion handler."""

    def __init__(self, config: TwentyClientConfig) -> None:
        self._config = config

    def _url(self, path: str) -> str:
        return f"{self._config.base_url}/rest/{path.lstrip('/')}"

    async def update_record(
        self,
        object_collection: str,
        record_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        """PATCH a single Twenty record with the supplied field values."""
        collection = _pluralize(object_collection)
        url = self._url(f"{collection}/{record_id}")

        logger.info(
            "[twenty] PATCH {} record {} with fields {}",
            collection,
            record_id,
            sorted(fields.keys()),
        )

        async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
            response = await client.patch(url, json=fields, headers=self._config.headers)

        return self._handle_response("update_record", response)

    async def create_note(self, payload: dict[str, Any]) -> Optional[str]:
        """Create a Twenty Note and return its id (or None on failure)."""
        url = self._url("notes")

        async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
            response = await client.post(url, json=payload, headers=self._config.headers)

        body = self._handle_response("create_note", response)
        note = body.get("data", {})
        if isinstance(note, dict):
            inner = note.get("createNote") or note.get("note") or note
            if isinstance(inner, dict):
                return inner.get("id")
        return None

    async def link_note(
        self,
        note_id: str,
        target_object: str,
        record_id: str,
    ) -> dict[str, Any]:
        """Attach a note to a record via a noteTarget (e.g. ``opportunityId``)."""
        url = self._url("noteTargets")
        target_field = f"{self._singularize(target_object)}Id"
        payload = {"noteId": note_id, target_field: record_id}

        async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
            response = await client.post(url, json=payload, headers=self._config.headers)

        return self._handle_response("link_note", response)

    @staticmethod
    def _singularize(object_name: str) -> str:
        name = (object_name or "").strip().strip("/")
        if name == "people":
            return "person"
        if name == "companies":
            return "company"
        if name.endswith("ies"):
            return f"{name[:-3]}y"
        if name.endswith("s"):
            return name[:-1]
        return name

    @staticmethod
    def _handle_response(action: str, response: httpx.Response) -> dict[str, Any]:
        if response.status_code >= 400:
            logger.error(
                "[twenty] {} failed with status {}: {}",
                action,
                response.status_code,
                response.text[:300],
            )
        response.raise_for_status()
        try:
            return response.json()
        except ValueError:
            return {}
