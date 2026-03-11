"""Integration tests for the Production Orchestrator pipeline.

Tests verify that the two-wave orchestration completes and all
output keys are populated in session state.
"""

import uuid

import pytest


@pytest.mark.llm
@pytest.mark.gcp
@pytest.mark.timeout(900)
async def test_parallel_execution(sample_brand_dna):
    """Full orchestrator completes within 15 minutes via InMemoryRunner."""
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    from brandforge.agents.production_orchestrator.agent import production_orchestrator

    runner = InMemoryRunner(
        agent=production_orchestrator,
        app_name="brandforge_test",
    )

    # Create session with brand_dna seeded via state= parameter.
    # Note: create_session returns a deep copy, so mutating session.state
    # after creation does NOT update the internal stored session.
    session = await runner.session_service.create_session(
        app_name="brandforge_test",
        user_id="test_user",
        state={"brand_dna": sample_brand_dna.model_dump(mode="json")},
    )

    user_message = types.Content(
        role="user",
        parts=[types.Part(text=(
            f"Generate all creative assets for campaign {sample_brand_dna.campaign_id}. "
            f"The brand is {sample_brand_dna.brand_name}. "
            f"Campaign goal: product launch. "
            f"Platforms: instagram, linkedin."
        ))],
    )

    events = []
    async for event in runner.run_async(
        user_id="test_user",
        session_id=session.id,
        new_message=user_message,
    ):
        events.append(event)

    assert len(events) > 0, "No events received from orchestrator"


@pytest.mark.llm
@pytest.mark.gcp
@pytest.mark.timeout(900)
async def test_all_output_keys_populated(sample_brand_dna):
    """After orchestrator completes, all 5 output keys are in session state."""
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    from brandforge.agents.production_orchestrator.agent import production_orchestrator

    runner = InMemoryRunner(
        agent=production_orchestrator,
        app_name="brandforge_test",
    )

    session = await runner.session_service.create_session(
        app_name="brandforge_test",
        user_id="test_user",
        state={"brand_dna": sample_brand_dna.model_dump(mode="json")},
    )

    user_message = types.Content(
        role="user",
        parts=[types.Part(text=(
            f"Generate all creative assets for campaign {sample_brand_dna.campaign_id}. "
            f"Brand: {sample_brand_dna.brand_name}. "
            f"Goal: product launch. Platforms: instagram, linkedin."
        ))],
    )

    async for event in runner.run_async(
        user_id="test_user",
        session_id=session.id,
        new_message=user_message,
    ):
        pass

    # Check the session state for output keys
    updated_session = await runner.session_service.get_session(
        app_name="brandforge_test",
        user_id="test_user",
        session_id=session.id,
    )

    expected_keys = [
        "video_scripts",
        "mood_board",
        "generated_images",
        "generated_videos",
        "approved_copy",
    ]

    state = updated_session.state
    for key in expected_keys:
        assert key in state, f"Output key '{key}' not found in session state"
