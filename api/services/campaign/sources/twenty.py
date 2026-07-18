import json
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from loguru import logger

from api.db import db_client
from api.services.campaign.source_sync import (
    CampaignSourceSyncService,
    ValidationError,
    ValidationResult,
)
from api.utils.credential_auth import build_auth_header


DEFAULT_PAGE_LIMIT = 100
MAX_PAGE_LIMIT = 500


@dataclass
class TwentySourceConfig:
    """Configuration for syncing Twenty records into Samvaad queued runs."""

    base_url: str
    credential_uuid: Optional[str] = None
    object_name: str = "people"
    filter: Optional[str] = None
    order_by: Optional[str] = None
    depth: int = 1
    page_limit: int = DEFAULT_PAGE_LIMIT
    max_records: Optional[int] = None
    phone_path: Optional[str] = None
    record_id_path: str = "id"
    context_mapping: dict[str, str] = field(default_factory=dict)


class TwentySyncService(CampaignSourceSyncService):
    """Sync Twenty CRM records into Samvaad campaign queued runs."""

    async def validate_source(
        self,
        source_id: str,
        organization_id: Optional[int] = None,
        source_config: Optional[dict[str, Any]] = None,
    ) -> ValidationResult:
        """Validate Twenty source config and fetch records for template checks."""
        try:
            config = self._parse_config(source_id, source_config)
            records = await self._fetch_records(config, organization_id)
            headers, rows = self._records_to_table(config, records)
        except ValueError as exc:
            return ValidationResult(
                is_valid=False,
                error=ValidationError(message=str(exc)),
            )

        if not rows:
            return ValidationResult(
                is_valid=False,
                error=ValidationError(
                    message="Twenty source did not return any records with phone numbers"
                ),
            )

        return self.validate_source_data(headers, rows)

    async def sync_source_data(self, campaign_id: int) -> int:
        """Fetch Twenty records and create Samvaad queued runs."""
        campaign = await db_client.get_campaign_by_id(campaign_id)
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        source_config = (campaign.orchestrator_metadata or {}).get("source_config")
        config = self._parse_config(campaign.source_id, source_config)
        records = await self._fetch_records(config, campaign.organization_id)

        queued_runs = []
        for record in records:
            context = self._record_to_context(config, record)
            phone_number = context.get("phone_number")
            if not phone_number:
                continue

            source_uuid = f"twenty_{config.object_name}_{context['twenty_record_id']}"
            queued_runs.append(
                {
                    "campaign_id": campaign_id,
                    "source_uuid": source_uuid,
                    "context_variables": context,
                    "state": "queued",
                }
            )

        if queued_runs:
            await db_client.bulk_create_queued_runs(queued_runs)
            logger.info(
                f"Created {len(queued_runs)} Twenty queued runs for campaign {campaign_id}"
            )

        await db_client.update_campaign(
            campaign_id=campaign_id,
            total_rows=len(queued_runs),
            source_sync_status="completed",
        )

        return len(queued_runs)

    def _parse_config(
        self, source_id: str, source_config: Optional[dict[str, Any]]
    ) -> TwentySourceConfig:
        raw_config: dict[str, Any] = {}

        if source_config:
            raw_config.update(source_config)
        else:
            try:
                parsed_source_id = json.loads(source_id)
            except json.JSONDecodeError:
                parsed_source_id = None
            if isinstance(parsed_source_id, dict):
                raw_config.update(parsed_source_id)

        if "object" in raw_config and "object_name" not in raw_config:
            raw_config["object_name"] = raw_config["object"]
        elif source_id and not source_id.strip().startswith("{"):
            raw_config.setdefault("object_name", source_id)

        base_url = str(raw_config.get("base_url") or "").strip().rstrip("/")
        if not base_url:
            raise ValueError("Twenty source requires source_config.base_url")

        object_name = str(raw_config.get("object_name") or "people").strip().strip("/")
        if not object_name:
            raise ValueError("Twenty source requires a non-empty object name")

        page_limit = int(raw_config.get("page_limit") or DEFAULT_PAGE_LIMIT)
        page_limit = max(1, min(page_limit, MAX_PAGE_LIMIT))

        max_records = raw_config.get("max_records")
        if max_records is not None:
            max_records = max(1, int(max_records))

        depth = int(raw_config.get("depth", 1))
        if depth < 0 or depth > 1:
            raise ValueError("Twenty REST depth must be 0 or 1")

        return TwentySourceConfig(
            base_url=base_url,
            credential_uuid=raw_config.get("credential_uuid"),
            object_name=object_name,
            filter=raw_config.get("filter"),
            order_by=raw_config.get("order_by"),
            depth=depth,
            page_limit=page_limit,
            max_records=max_records,
            phone_path=raw_config.get("phone_path"),
            record_id_path=raw_config.get("record_id_path", "id"),
            context_mapping=raw_config.get("context_mapping") or {},
        )

    async def _fetch_records(
        self, config: TwentySourceConfig, organization_id: Optional[int]
    ) -> list[dict[str, Any]]:
        headers = {"Accept": "application/json"}
        if config.credential_uuid:
            if organization_id is None:
                raise ValueError("organization_id is required for credential lookup")
            credential = await db_client.get_credential_by_uuid(
                config.credential_uuid, organization_id
            )
            if not credential:
                raise ValueError("Twenty credential not found")
            headers.update(build_auth_header(credential))

        records: list[dict[str, Any]] = []
        starting_after: Optional[str] = None

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                query = {
                    "limit": config.page_limit,
                    "depth": config.depth,
                }
                if config.filter:
                    query["filter"] = config.filter
                if config.order_by:
                    query["order_by"] = config.order_by
                if starting_after:
                    query["starting_after"] = starting_after

                url = f"{config.base_url}/rest/{config.object_name}?{urlencode(query)}"
                response = await client.get(url, headers=headers)
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    raise ValueError(
                        f"Twenty API request failed: {exc.response.status_code}"
                    ) from exc

                body = response.json()
                page_records = self._extract_records(body, config.object_name)
                records.extend(page_records)

                if config.max_records and len(records) >= config.max_records:
                    return records[: config.max_records]

                page_info = body.get("pageInfo") or {}
                if not page_info.get("hasNextPage"):
                    return records
                starting_after = page_info.get("endCursor")
                if not starting_after:
                    return records

    def _extract_records(self, body: dict[str, Any], object_name: str) -> list[dict]:
        data = body.get("data")
        if not isinstance(data, dict):
            raise ValueError("Twenty API response is missing data object")

        records = data.get(object_name)
        if records is None:
            records = data.get(self._singularize(object_name))
        if records is None:
            records = next((v for v in data.values() if isinstance(v, list)), None)

        if not isinstance(records, list):
            raise ValueError("Twenty API response did not contain a record list")

        return [record for record in records if isinstance(record, dict)]

    def _records_to_table(
        self, config: TwentySourceConfig, records: list[dict[str, Any]]
    ) -> tuple[list[str], list[list[str]]]:
        contexts = [self._record_to_context(config, record) for record in records]
        contexts = [context for context in contexts if context.get("phone_number")]
        headers = sorted({key for context in contexts for key in context.keys()})
        rows = [[str(context.get(header, "")) for header in headers] for context in contexts]
        return headers, rows

    def _record_to_context(
        self, config: TwentySourceConfig, record: dict[str, Any]
    ) -> dict[str, Any]:
        record_id = self._get_path(record, config.record_id_path)
        if not record_id:
            raise ValueError(
                f"Twenty record is missing id at path '{config.record_id_path}'"
            )

        context: dict[str, Any] = {
            "twenty_object": self._singularize(config.object_name),
            "twenty_record_id": str(record_id),
        }

        phone_number = self._extract_phone(config, record)
        if phone_number:
            context["phone_number"] = phone_number

        context.update(self._default_context(config, record))
        for output_key, source_path in config.context_mapping.items():
            value = self._get_path(record, source_path)
            if value is not None:
                context[output_key] = value

        return context

    def _default_context(
        self, config: TwentySourceConfig, record: dict[str, Any]
    ) -> dict[str, Any]:
        object_name = self._singularize(config.object_name)
        context: dict[str, Any] = {}

        if object_name == "person":
            context["twenty_person_id"] = str(record.get("id", ""))
            context["first_name"] = self._get_path(record, "name.firstName") or record.get(
                "nameFirstName", ""
            )
            context["last_name"] = self._get_path(record, "name.lastName") or record.get(
                "nameLastName", ""
            )
            context["twenty_company_id"] = record.get("companyId") or ""
            context["company_name"] = self._get_path(record, "company.name") or ""
        elif object_name == "opportunity":
            context["twenty_opportunity_id"] = str(record.get("id", ""))
            context["opportunity_name"] = record.get("name", "")
            context["twenty_company_id"] = record.get("companyId") or ""
            context["company_name"] = self._get_path(record, "company.name") or ""
            context["twenty_person_id"] = record.get("pointOfContactId") or ""
            context["first_name"] = (
                self._get_path(record, "pointOfContact.name.firstName")
                or self._get_path(record, "pointOfContact.nameFirstName")
                or ""
            )
            context["last_name"] = (
                self._get_path(record, "pointOfContact.name.lastName")
                or self._get_path(record, "pointOfContact.nameLastName")
                or ""
            )

        return {key: value for key, value in context.items() if value not in (None, "")}

    def _extract_phone(
        self, config: TwentySourceConfig, record: dict[str, Any]
    ) -> Optional[str]:
        candidates = []
        if config.phone_path:
            candidates.append(self._get_path(record, config.phone_path))

        candidates.extend(
            [
                self._get_path(record, "phones"),
                self._get_path(record, "phone"),
                self._get_path(record, "pointOfContact.phones"),
                self._get_path(record, "person.phones"),
            ]
        )

        for candidate in candidates:
            phone = self._normalize_phone(candidate)
            if phone:
                return phone

        number = (
            record.get("phonesPrimaryPhoneNumber")
            or self._get_path(record, "pointOfContact.phonesPrimaryPhoneNumber")
            or self._get_path(record, "person.phonesPrimaryPhoneNumber")
        )
        calling_code = (
            record.get("phonesPrimaryPhoneCallingCode")
            or self._get_path(record, "pointOfContact.phonesPrimaryPhoneCallingCode")
            or self._get_path(record, "person.phonesPrimaryPhoneCallingCode")
        )
        return self._combine_phone(calling_code, number)

    def _normalize_phone(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str):
            return value if value.startswith("+") else None
        if isinstance(value, dict):
            number = (
                value.get("primaryPhoneNumber")
                or value.get("phoneNumber")
                or value.get("number")
            )
            calling_code = (
                value.get("primaryPhoneCallingCode")
                or value.get("callingCode")
                or value.get("countryCode")
            )
            return self._combine_phone(calling_code, number)
        return None

    def _combine_phone(self, calling_code: Any, number: Any) -> Optional[str]:
        if not number:
            return None
        number_str = str(number).strip()
        if number_str.startswith("+"):
            return number_str
        if not calling_code:
            return None
        calling_code_str = str(calling_code).strip()
        if not calling_code_str.startswith("+"):
            calling_code_str = f"+{calling_code_str}"
        return f"{calling_code_str}{number_str}"

    def _get_path(self, data: dict[str, Any], path: str) -> Any:
        current: Any = data
        for part in path.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
            if current is None:
                return None
        return current

    def _singularize(self, object_name: str) -> str:
        if object_name == "people":
            return "person"
        if object_name.endswith("ies"):
            return f"{object_name[:-3]}y"
        if object_name.endswith("s"):
            return object_name[:-1]
        return object_name
