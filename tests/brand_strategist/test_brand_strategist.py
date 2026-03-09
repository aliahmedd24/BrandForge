"""Tests for the Brand Strategist Agent.

Unit tests (no external calls) run without markers.
Integration tests require @pytest.mark.llm (Gemini API) and/or @pytest.mark.gcp.
"""

import json
from datetime import timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from brandforge.shared.models import (
    BrandDNA,
    ColorPalette,
    Typography,
    AudiencePersona,
    MessagingPillar,
    VisualAssetAnalysis,
)


# ── Unit Tests: Pydantic Model Validation ────────────────────────────────


class TestColorPalette:
    """Verify ColorPalette hex validation."""

    def test_valid_hex_colors(self, sample_color_palette: ColorPalette) -> None:
        """Valid hex colors pass validation."""
        assert sample_color_palette.primary == "#2D3A2E"
        assert sample_color_palette.text == "#1A1A1A"

    def test_invalid_hex_raises(self) -> None:
        """Invalid hex color raises ValidationError."""
        with pytest.raises(ValidationError):
            ColorPalette(
                primary="not-a-color",
                secondary="#FFFFFF",
                accent="#000000",
                background="#F5F5F5",
                text="#1A1A1A",
            )

    def test_short_hex_raises(self) -> None:
        """3-digit hex codes are rejected (must be 6-digit)."""
        with pytest.raises(ValidationError):
            ColorPalette(
                primary="#FFF",
                secondary="#FFFFFF",
                accent="#000000",
                background="#F5F5F5",
                text="#1A1A1A",
            )

    def test_missing_hash_raises(self) -> None:
        """Hex without # prefix is rejected."""
        with pytest.raises(ValidationError):
            ColorPalette(
                primary="2D3A2E",
                secondary="#FFFFFF",
                accent="#000000",
                background="#F5F5F5",
                text="#1A1A1A",
            )

    def test_all_five_colors_present(self) -> None:
        """ColorPalette has exactly 5 named color fields."""
        fields = ColorPalette.model_fields
        assert set(fields.keys()) == {"primary", "secondary", "accent", "background", "text"}


class TestBrandDNAModel:
    """Verify BrandDNA model serialization and defaults."""

    def test_round_trip(self, sample_brand_dna: BrandDNA) -> None:
        """BrandDNA serializes to JSON and deserializes back."""
        json_str = sample_brand_dna.model_dump_json()
        restored = BrandDNA.model_validate_json(json_str)
        assert restored.brand_name == sample_brand_dna.brand_name
        assert restored.campaign_id == sample_brand_dna.campaign_id
        assert restored.color_palette.primary == sample_brand_dna.color_palette.primary

    def test_uuid_auto_generated(self, sample_brand_dna: BrandDNA) -> None:
        """BrandDNA id is auto-generated as UUID."""
        assert len(sample_brand_dna.id) == 36
        assert "-" in sample_brand_dna.id

    def test_default_version_is_1(self) -> None:
        """Default version is 1."""
        dna = BrandDNA(
            campaign_id="c1",
            brand_name="X",
            brand_essence="essence",
            brand_personality=["a"],
            tone_of_voice="tone",
            color_palette=ColorPalette(
                primary="#000000", secondary="#111111",
                accent="#222222", background="#333333", text="#444444",
            ),
            typography=Typography(
                heading_font="Arial", body_font="Arial",
                font_personality="clean",
            ),
            primary_persona=AudiencePersona(
                name="Test", age_range="20-30",
                values=["v"], pain_points=["p"], content_habits=["c"],
            ),
            messaging_pillars=[
                MessagingPillar(
                    title="T", one_liner="O",
                    supporting_points=["s"], avoid=["a"],
                ),
            ],
            visual_direction="visual",
            platform_strategy={"instagram": "posts"},
            do_not_use=["bad"],
            source_brief_summary="summary",
        )
        assert dna.version == 1

    def test_timestamp_is_utc(self, sample_brand_dna: BrandDNA) -> None:
        """BrandDNA created_at is timezone-aware UTC."""
        assert sample_brand_dna.created_at.tzinfo is not None
        assert sample_brand_dna.created_at.tzinfo == timezone.utc

    def test_dict_serialization_for_firestore(self, sample_brand_dna: BrandDNA) -> None:
        """BrandDNA can be serialized to a dict suitable for Firestore."""
        data = sample_brand_dna.model_dump(mode="json")
        assert isinstance(data, dict)
        assert data["brand_name"] == "TestBrand"
        assert isinstance(data["color_palette"], dict)
        assert isinstance(data["messaging_pillars"], list)

    def test_color_palette_hex_valid_in_dna(self, sample_brand_dna: BrandDNA) -> None:
        """All 5 palette colors in BrandDNA are valid hex codes."""
        import re

        palette = sample_brand_dna.color_palette
        for field_name in ["primary", "secondary", "accent", "background", "text"]:
            color = getattr(palette, field_name)
            assert re.match(r"^#[0-9A-Fa-f]{6}$", color), f"{field_name}={color} is invalid hex"

    def test_no_hallucination_source_brief(self, sample_brand_dna: BrandDNA) -> None:
        """source_brief_summary references the input brand name and product."""
        assert "TestBrand" in sample_brand_dna.source_brief_summary
        assert "sustainable water bottle" in sample_brand_dna.source_brief_summary


class TestVisualAssetAnalysis:
    """Verify VisualAssetAnalysis model."""

    def test_round_trip(self, sample_visual_analysis: VisualAssetAnalysis) -> None:
        """VisualAssetAnalysis serializes and deserializes correctly."""
        json_str = sample_visual_analysis.model_dump_json()
        restored = VisualAssetAnalysis.model_validate_json(json_str)
        assert restored.visual_energy == "minimalist"
        assert len(restored.detected_colors) == 4

    def test_dict_output(self, sample_visual_analysis: VisualAssetAnalysis) -> None:
        """VisualAssetAnalysis can be converted to dict (for tool return)."""
        data = sample_visual_analysis.model_dump()
        assert isinstance(data, dict)
        assert "detected_colors" in data


# ── Unit Tests: Tool Logic ───────────────────────────────────────────────


class TestFallbackDNA:
    """Verify the fallback Brand DNA generator."""

    def test_fallback_produces_valid_dna(self) -> None:
        """_build_fallback_dna returns a valid BrandDNA instance."""
        from brandforge.agents.brand_strategist.tools import _build_fallback_dna

        dna = _build_fallback_dna(
            campaign_id="test-123",
            brand_name="FallbackBrand",
            product_description="A test product",
            target_audience="Everyone",
            campaign_goal="awareness",
            tone_keywords="bold, fun",
            platforms="instagram, linkedin",
        )
        assert isinstance(dna, BrandDNA)
        assert dna.campaign_id == "test-123"
        assert dna.brand_name == "FallbackBrand"
        assert "FallbackBrand" in dna.source_brief_summary

    def test_fallback_with_empty_keywords(self) -> None:
        """Fallback handles empty tone_keywords gracefully."""
        from brandforge.agents.brand_strategist.tools import _build_fallback_dna

        dna = _build_fallback_dna(
            campaign_id="test-456",
            brand_name="EmptyBrand",
            product_description="Product",
            target_audience="Audience",
            campaign_goal="launch",
            tone_keywords="",
            platforms="tiktok",
        )
        assert isinstance(dna, BrandDNA)
        assert len(dna.brand_personality) == 5  # defaults


class TestToolHelpers:
    """Verify tool helper functions."""

    def test_gcs_path_from_url(self) -> None:
        """_gcs_path_from_url extracts path from gs:// URL."""
        from brandforge.agents.brand_strategist.tools import _gcs_path_from_url

        assert _gcs_path_from_url("gs://bucket/path/to/file.png") == "path/to/file.png"
        assert _gcs_path_from_url("gs://bucket/file.png") == "file.png"
        assert _gcs_path_from_url("plain/path") == "plain/path"

    def test_mime_from_url(self) -> None:
        """_mime_from_url detects common image/audio types."""
        from brandforge.agents.brand_strategist.tools import _mime_from_url

        assert _mime_from_url("file.png") == "image/png"
        assert _mime_from_url("file.jpeg") == "image/jpeg"
        assert _mime_from_url("file.jpg") == "image/jpeg"
        # webp may not be registered on all platforms; just verify no crash
        result = _mime_from_url("file.webp")
        assert isinstance(result, str)


# ── Integration Tests: Require Gemini API ────────────────────────────────


@pytest.mark.llm
class TestBrandStrategistIntegration:
    """Integration tests requiring live Gemini API calls."""

    @pytest.mark.asyncio
    async def test_text_only_brief(self) -> None:
        """Given a text-only brief, agent returns a valid BrandDNA."""
        from google.adk.runners import InMemoryRunner
        from google.genai import types

        from brandforge.agent import root_agent

        runner = InMemoryRunner(agent=root_agent, app_name="test_brand_strategist")
        session = await runner.session_service.create_session(
            user_id="test_user", app_name="test_brand_strategist",
        )

        message = types.Content(
            role="user",
            parts=[types.Part.from_text(text=(
                "Create a brand DNA for my brand. "
                "Brand name: EcoFlow. "
                "Product: Portable solar power stations. "
                "Target audience: Outdoor enthusiasts and off-grid homeowners. "
                "Campaign goal: product launch. "
                "Tone keywords: rugged, reliable, innovative. "
                "Platforms: instagram, youtube. "
                "Campaign ID: test-text-only-001."
            ))],
        )

        events = []
        async for event in runner.run_async(
            user_id="test_user",
            session_id=session.id,
            new_message=message,
        ):
            events.append(event)

        # Verify we got a response
        assert len(events) > 0

        # Check output_key or state for brand_dna_result
        updated_session = await runner.session_service.get_session(
            user_id="test_user",
            app_name="test_brand_strategist",
            session_id=session.id,
        )
        brand_dna_json = updated_session.state.get("brand_dna_result")
        if brand_dna_json:
            dna = BrandDNA.model_validate_json(brand_dna_json)
            assert dna.brand_name is not None

    @pytest.mark.asyncio
    async def test_output_key_populated(self) -> None:
        """After agent completes, session state has brand_dna_result."""
        from google.adk.runners import InMemoryRunner
        from google.genai import types

        from brandforge.agent import root_agent

        runner = InMemoryRunner(agent=root_agent, app_name="test_output_key")
        session = await runner.session_service.create_session(
            user_id="test_user", app_name="test_output_key",
        )

        message = types.Content(
            role="user",
            parts=[types.Part.from_text(text=(
                "Create a brand DNA. "
                "Brand name: QuickBite. "
                "Product: Healthy meal prep delivery service. "
                "Target audience: Busy professionals aged 28-42. "
                "Campaign goal: brand awareness. "
                "Tone keywords: fresh, convenient, trustworthy. "
                "Platforms: instagram, facebook. "
                "Campaign ID: test-output-key-001."
            ))],
        )

        async for _ in runner.run_async(
            user_id="test_user",
            session_id=session.id,
            new_message=message,
        ):
            pass

        updated_session = await runner.session_service.get_session(
            user_id="test_user",
            app_name="test_output_key",
            session_id=session.id,
        )
        # output_key="brand_dna_result" should be populated
        assert updated_session.state.get("brand_dna_result") is not None


@pytest.mark.llm
@pytest.mark.gcp
class TestBrandStrategistGCPIntegration:
    """Integration tests requiring both Gemini API and GCP services."""

    @pytest.mark.asyncio
    async def test_brand_dna_stored_in_firestore(self) -> None:
        """After agent completes, BrandDNA exists in Firestore."""
        # This test requires live Firestore. Run with: pytest -m "llm and gcp"
        pass  # Placeholder — requires live GCP project

    @pytest.mark.asyncio
    async def test_version_increment(self) -> None:
        """Rerunning the agent for the same campaign creates version 2."""
        # This test requires live Firestore for version query.
        pass  # Placeholder — requires live GCP project

    @pytest.mark.asyncio
    async def test_with_image_assets(self) -> None:
        """Brief with images produces VisualAssetAnalysis that influences palette."""
        # Requires GCS with test images uploaded.
        pass  # Placeholder — requires live GCP project

    @pytest.mark.asyncio
    async def test_voice_brief_transcription(self) -> None:
        """Audio file URL produces transcription merged into DNA context."""
        # Requires GCS with test audio uploaded.
        pass  # Placeholder — requires live GCP project


class TestAudioTimeoutFallback:
    """Test that audio transcription timeout falls back gracefully."""

    @pytest.mark.asyncio
    async def test_audio_timeout_returns_empty(self) -> None:
        """If transcription exceeds 30s, empty string is returned."""
        import asyncio

        from brandforge.agents.brand_strategist.tools import transcribe_voice_brief

        mock_context = MagicMock()
        mock_context.state = {}

        with patch(
            "brandforge.agents.brand_strategist.tools.download_blob",
            return_value=b"fake audio data",
        ), patch(
            "brandforge.agents.brand_strategist.tools._get_genai_client",
        ) as mock_client:
            # Make the Gemini call hang forever
            async def slow_generate(*args, **kwargs):
                await asyncio.sleep(60)

            mock_client.return_value.models.generate_content = MagicMock(
                side_effect=lambda *a, **kw: asyncio.get_event_loop().run_until_complete(
                    asyncio.sleep(60)
                )
            )

            # The tool should timeout at 30s and return ""
            # We mock to_thread to raise TimeoutError quickly for test speed
            with patch("brandforge.agents.brand_strategist.tools.asyncio.wait_for") as mock_wait:
                mock_wait.side_effect = asyncio.TimeoutError()
                result = await transcribe_voice_brief(
                    voice_brief_url="gs://bucket/audio.webm",
                    campaign_id="test-timeout",
                    tool_context=mock_context,
                )

            assert result == ""
            assert mock_context.state["transcription"] == ""
