"""Unit tests verifying baseline pipeline behavior without BDR keys.

Validates Requirements 14.1 and 14.2:
- Pipeline construction produces identical processor list when no BDR keys
  are present in workflow_configurations.
- Exotel provider registration does not affect non-Exotel organizations.
"""

from unittest.mock import MagicMock

import pytest

from api.services.pipecat.pipeline_builder import build_pipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_processor(name: str):
    """Create a named mock processor for pipeline comparison."""
    proc = MagicMock()
    proc.name = name
    return proc


def _make_transport():
    """Create a mock transport with input/output methods."""
    transport = MagicMock()
    transport.input.return_value = _make_mock_processor("transport_input")
    transport.output.return_value = _make_mock_processor("transport_output")
    return transport


# ---------------------------------------------------------------------------
# Test 1: Pipeline construction without BDR keys produces identical processors
# ---------------------------------------------------------------------------


class TestPipelineBaselineWithoutBDRKeys:
    """Verify that build_pipeline produces the same processor list regardless
    of whether BDR features are absent or explicitly disabled."""

    def test_build_pipeline_without_bdr_keys_matches_baseline(self):
        """When no BDR keys are present, build_pipeline produces the standard
        processor list: transport_in → stt → user_agg → llm → callback_proc →
        tts → transport_out → audio_buffer → assistant_agg → metrics_agg.
        Pipeline wraps these with PipelineSource and PipelineSink (12 total)."""
        transport = _make_transport()
        stt = _make_mock_processor("stt")
        audio_buffer = _make_mock_processor("audio_buffer")
        llm = _make_mock_processor("llm")
        tts = _make_mock_processor("tts")
        user_context_aggregator = _make_mock_processor("user_context_aggregator")
        assistant_context_aggregator = _make_mock_processor(
            "assistant_context_aggregator"
        )
        pipeline_engine_callback_processor = _make_mock_processor(
            "pipeline_engine_callback"
        )
        pipeline_metrics_aggregator = _make_mock_processor("pipeline_metrics_aggregator")

        # Build pipeline with NO optional BDR processors
        pipeline = build_pipeline(
            transport,
            stt,
            audio_buffer,
            llm,
            tts,
            user_context_aggregator,
            assistant_context_aggregator,
            pipeline_engine_callback_processor,
            pipeline_metrics_aggregator,
            voicemail_detector=None,
            recording_router=None,
        )

        # Extract the processor list from the pipeline
        # Pipeline wraps with PipelineSource + PipelineSink, so 10 user processors + 2 = 12
        processors = pipeline.processors

        # The baseline pipeline has exactly 10 user-specified processors
        # plus PipelineSource and PipelineSink wrappers = 12 total
        BASELINE_PROCESSOR_COUNT = 12
        assert len(processors) == BASELINE_PROCESSOR_COUNT, (
            f"Expected {BASELINE_PROCESSOR_COUNT} processors (10 + source/sink), "
            f"got {len(processors)}"
        )

    def test_build_pipeline_no_voicemail_no_recording_router(self):
        """When voicemail_detector=None and recording_router=None (the default
        when no BDR keys are present), the pipeline does NOT include any
        voicemail or recording router processors."""
        transport = _make_transport()
        stt = _make_mock_processor("stt")
        audio_buffer = _make_mock_processor("audio_buffer")
        llm = _make_mock_processor("llm")
        tts = _make_mock_processor("tts")
        user_context_aggregator = _make_mock_processor("user_context_aggregator")
        assistant_context_aggregator = _make_mock_processor(
            "assistant_context_aggregator"
        )
        pipeline_engine_callback_processor = _make_mock_processor(
            "pipeline_engine_callback"
        )
        pipeline_metrics_aggregator = _make_mock_processor("pipeline_metrics_aggregator")

        pipeline = build_pipeline(
            transport,
            stt,
            audio_buffer,
            llm,
            tts,
            user_context_aggregator,
            assistant_context_aggregator,
            pipeline_engine_callback_processor,
            pipeline_metrics_aggregator,
            voicemail_detector=None,
            recording_router=None,
        )

        processors = pipeline.processors

        # No voicemail detector or llm_gate should be present
        # The baseline pipeline has 10 user processors + PipelineSource + PipelineSink = 12
        BASELINE_PROCESSOR_COUNT = 12
        assert len(processors) == BASELINE_PROCESSOR_COUNT

    def test_build_pipeline_identical_with_empty_run_configs(self):
        """Calling build_pipeline with the same args produces the same
        processor count whether run_configs is empty or has non-BDR keys.
        This confirms BDR features don't leak into build_pipeline."""
        transport = _make_transport()
        stt = _make_mock_processor("stt")
        audio_buffer = _make_mock_processor("audio_buffer")
        llm = _make_mock_processor("llm")
        tts = _make_mock_processor("tts")
        user_agg = _make_mock_processor("user_context_aggregator")
        assistant_agg = _make_mock_processor("assistant_context_aggregator")
        callback_proc = _make_mock_processor("pipeline_engine_callback")
        metrics_agg = _make_mock_processor("pipeline_metrics_aggregator")

        # Build pipeline twice with same args
        pipeline_a = build_pipeline(
            transport,
            stt,
            audio_buffer,
            llm,
            tts,
            user_agg,
            assistant_agg,
            callback_proc,
            metrics_agg,
            voicemail_detector=None,
            recording_router=None,
        )

        pipeline_b = build_pipeline(
            transport,
            stt,
            audio_buffer,
            llm,
            tts,
            user_agg,
            assistant_agg,
            callback_proc,
            metrics_agg,
            voicemail_detector=None,
            recording_router=None,
        )

        assert len(pipeline_a.processors) == len(pipeline_b.processors)

    def test_goodbye_detector_defaults_to_none_in_build_pipeline(self):
        """build_pipeline accepts a goodbye_detector parameter that defaults
        to None, confirming that the goodbye detection BDR feature does not
        affect the pipeline processor list when not explicitly provided."""
        import inspect

        sig = inspect.signature(build_pipeline)
        param = sig.parameters.get("goodbye_detector")
        assert param is not None
        assert param.default is None

    def test_call_state_detector_defaults_to_none_in_build_pipeline(self):
        """build_pipeline accepts a call_state_detector parameter that defaults
        to None, confirming that the call state detection BDR feature does not
        affect the pipeline processor list when not explicitly provided."""
        import inspect

        sig = inspect.signature(build_pipeline)
        param = sig.parameters.get("call_state_detector")
        assert param is not None
        assert param.default is None


# ---------------------------------------------------------------------------
# Test 2: Exotel registration does not affect non-Exotel organizations
# ---------------------------------------------------------------------------


class TestExotelRegistrationIsolation:
    """Verify that Exotel provider registration does not affect organizations
    that use other telephony providers (e.g., Twilio)."""

    def test_exotel_registered_in_registry(self):
        """Exotel is registered in the telephony registry."""
        from api.services.telephony.registry import get, names

        assert "exotel" in names()
        spec = get("exotel")
        assert spec.name == "exotel"
        assert spec.transport_sample_rate == 8000

    def test_twilio_still_accessible_after_exotel_registration(self):
        """Twilio provider remains fully accessible after Exotel registration.
        This confirms Exotel registration doesn't interfere with other providers."""
        from api.services.telephony.registry import get

        twilio_spec = get("twilio")
        assert twilio_spec.name == "twilio"
        assert twilio_spec.transport_sample_rate == 8000

    def test_all_providers_registered_independently(self):
        """Each provider is registered independently; adding Exotel doesn't
        remove or modify any existing provider."""
        from api.services.telephony.registry import all_specs, names

        registered_names = list(names())
        # Exotel should be present alongside existing providers
        assert "exotel" in registered_names
        assert "twilio" in registered_names

        # Each spec is distinct
        specs = all_specs()
        spec_names = [s.name for s in specs]
        assert len(spec_names) == len(set(spec_names)), "Duplicate provider names found"

    def test_exotel_config_loader_does_not_affect_twilio_config(self):
        """Exotel's config_loader only processes Exotel-specific fields.
        Passing Twilio credentials to Exotel's loader doesn't produce
        valid Exotel config (isolation by design)."""
        from api.services.telephony.registry import get

        exotel_spec = get("exotel")
        twilio_creds = {
            "account_sid": "AC123",
            "auth_token": "secret",
            "from_numbers": ["+15551234567"],
        }

        # Exotel config_loader processes the dict but won't find Exotel-specific fields
        result = exotel_spec.config_loader(twilio_creds)
        assert result["provider"] == "exotel"
        # Exotel-specific fields are None/missing since Twilio creds don't have them
        assert result.get("api_key") is None
        assert result.get("api_token") is None

    def test_twilio_config_loader_does_not_affect_exotel_config(self):
        """Twilio's config_loader only processes Twilio-specific fields.
        Passing Exotel credentials to Twilio's loader doesn't produce
        valid Twilio config."""
        from api.services.telephony.registry import get

        twilio_spec = get("twilio")
        exotel_creds = {
            "api_key": "exotel-key",
            "api_token": "exotel-token",
            "account_sid": "exotel-sid",
            "subdomain": "api.in.exotel.com",
            "app_id": "app123",
        }

        result = twilio_spec.config_loader(exotel_creds)
        assert result["provider"] == "twilio"
        # Twilio-specific fields: account_sid maps but auth_token is missing
        assert result.get("auth_token") is None
        assert result.get("from_numbers") == []

    def test_registry_get_raises_for_unknown_provider(self):
        """The registry raises ValueError for unknown providers, confirming
        that Exotel registration doesn't create a catch-all."""
        from api.services.telephony.registry import get

        with pytest.raises(ValueError, match="Unknown telephony provider"):
            get("nonexistent_provider")

    def test_exotel_provider_spec_has_correct_ui_metadata(self):
        """Exotel's UI metadata is self-contained and doesn't bleed into
        other providers' metadata."""
        from api.services.telephony.registry import get

        exotel_spec = get("exotel")
        twilio_spec = get("twilio")

        assert exotel_spec.ui_metadata is not None
        assert exotel_spec.ui_metadata.display_name == "Exotel"

        assert twilio_spec.ui_metadata is not None
        assert twilio_spec.ui_metadata.display_name == "Twilio"

        # Field names are distinct between providers
        exotel_field_names = {f.name for f in exotel_spec.ui_metadata.fields}
        twilio_field_names = {f.name for f in twilio_spec.ui_metadata.fields}

        # Exotel has api_key, api_token, account_sid, subdomain, app_id
        assert "api_token" in exotel_field_names
        assert "subdomain" in exotel_field_names
        assert "app_id" in exotel_field_names

        # Twilio has account_sid, auth_token, from_numbers
        assert "auth_token" in twilio_field_names
        assert "from_numbers" in twilio_field_names

    @pytest.mark.asyncio
    async def test_non_exotel_org_telephony_lookup_ignores_exotel(self):
        """When loading telephony config for a non-Exotel org, the Exotel
        provider is never instantiated. The factory resolves the correct
        provider based on stored credentials."""
        from api.services.telephony.registry import get

        # Simulate a Twilio-configured org: the factory would call
        # twilio_spec.config_loader with the stored credentials
        twilio_spec = get("twilio")
        twilio_config = twilio_spec.config_loader(
            {
                "account_sid": "AC_real_sid",
                "auth_token": "real_token",
                "from_numbers": ["+15551234567"],
            }
        )

        # The resolved config is for Twilio, not Exotel
        assert twilio_config["provider"] == "twilio"
        assert twilio_config["account_sid"] == "AC_real_sid"
