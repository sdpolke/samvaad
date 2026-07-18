from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.campaign.sources.twenty import TwentySyncService
from api.services.campaign.source_sync_factory import get_sync_service


def test_get_sync_service_supports_twenty():
    assert isinstance(get_sync_service("twenty"), TwentySyncService)


def test_twenty_people_record_maps_to_campaign_context():
    service = TwentySyncService()
    config = service._parse_config(
        "people",
        {
            "base_url": "http://localhost:3000",
            "object": "people",
        },
    )

    context = service._record_to_context(
        config,
        {
            "id": "person-1",
            "name": {"firstName": "Brian", "lastName": "Chesky"},
            "phones": {
                "primaryPhoneCallingCode": "+1",
                "primaryPhoneNumber": "123456789",
            },
            "companyId": "company-1",
            "company": {"name": "Airbnb"},
        },
    )

    assert context["phone_number"] == "+1123456789"
    assert context["twenty_object"] == "person"
    assert context["twenty_record_id"] == "person-1"
    assert context["twenty_person_id"] == "person-1"
    assert context["twenty_company_id"] == "company-1"
    assert context["company_name"] == "Airbnb"
    assert context["first_name"] == "Brian"


def test_twenty_opportunity_record_maps_point_of_contact_phone():
    service = TwentySyncService()
    config = service._parse_config(
        "opportunities",
        {
            "base_url": "http://localhost:3000",
            "object": "opportunities",
        },
    )

    context = service._record_to_context(
        config,
        {
            "id": "opportunity-1",
            "name": "Enterprise Upgrade",
            "companyId": "company-1",
            "company": {"name": "Airbnb"},
            "pointOfContactId": "person-1",
            "pointOfContact": {
                "name": {"firstName": "Brian", "lastName": "Chesky"},
                "phones": {
                    "primaryPhoneCallingCode": "+1",
                    "primaryPhoneNumber": "123456789",
                },
            },
        },
    )

    assert context["phone_number"] == "+1123456789"
    assert context["twenty_object"] == "opportunity"
    assert context["twenty_record_id"] == "opportunity-1"
    assert context["twenty_opportunity_id"] == "opportunity-1"
    assert context["twenty_person_id"] == "person-1"
    assert context["twenty_company_id"] == "company-1"
    assert context["opportunity_name"] == "Enterprise Upgrade"


@pytest.mark.asyncio
async def test_validate_source_fetches_twenty_records():
    service = TwentySyncService()

    with patch.object(
        service,
        "_fetch_records",
        AsyncMock(
            return_value=[
                {
                    "id": "person-1",
                    "phones": {
                        "primaryPhoneCallingCode": "+1",
                        "primaryPhoneNumber": "123456789",
                    },
                }
            ]
        ),
    ):
        result = await service.validate_source(
            "people",
            organization_id=1,
            source_config={"base_url": "http://localhost:3000"},
        )

    assert result.is_valid is True
    assert "phone_number" in result.headers
    phone_idx = result.headers.index("phone_number")
    assert result.rows[0][phone_idx] == "+1123456789"


@pytest.mark.asyncio
async def test_sync_source_data_creates_queued_runs():
    service = TwentySyncService()
    campaign = SimpleNamespace(
        id=7,
        organization_id=3,
        source_id="people",
        orchestrator_metadata={
            "source_config": {
                "base_url": "http://localhost:3000",
                "object": "people",
            }
        },
    )

    records = [
        {
            "id": "person-1",
            "phones": {
                "primaryPhoneCallingCode": "+1",
                "primaryPhoneNumber": "123456789",
            },
        }
    ]

    with (
        patch("api.services.campaign.sources.twenty.db_client") as mock_db,
        patch.object(service, "_fetch_records", AsyncMock(return_value=records)),
    ):
        mock_db.get_campaign_by_id = AsyncMock(return_value=campaign)
        mock_db.bulk_create_queued_runs = AsyncMock()
        mock_db.update_campaign = AsyncMock()

        synced_count = await service.sync_source_data(campaign_id=7)

    assert synced_count == 1
    mock_db.bulk_create_queued_runs.assert_awaited_once()
    queued_runs = mock_db.bulk_create_queued_runs.await_args.args[0]
    assert queued_runs[0]["campaign_id"] == 7
    assert queued_runs[0]["source_uuid"] == "twenty_people_person-1"
    assert queued_runs[0]["context_variables"]["phone_number"] == "+1123456789"
    mock_db.update_campaign.assert_awaited_once_with(
        campaign_id=7,
        total_rows=1,
        source_sync_status="completed",
    )


@pytest.mark.asyncio
async def test_fetch_records_uses_credential_header():
    service = TwentySyncService()
    config = service._parse_config(
        "people",
        {
            "base_url": "http://localhost:3000",
            "credential_uuid": "cred-1",
        },
    )

    credential = SimpleNamespace(
        credential_type="bearer_token",
        credential_data={"token": "twenty-token"},
    )
    response = MagicMock()
    response.json.return_value = {
        "data": {"people": []},
        "pageInfo": {"hasNextPage": False},
    }
    response.raise_for_status.return_value = None

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("api.services.campaign.sources.twenty.db_client") as mock_db,
        patch(
            "api.services.campaign.sources.twenty.httpx.AsyncClient",
            return_value=mock_client,
        ),
    ):
        mock_db.get_credential_by_uuid = AsyncMock(return_value=credential)
        records = await service._fetch_records(config, organization_id=3)

    assert records == []
    mock_client.get.assert_awaited_once()
    assert mock_client.get.await_args.kwargs["headers"]["Authorization"] == (
        "Bearer twenty-token"
    )
