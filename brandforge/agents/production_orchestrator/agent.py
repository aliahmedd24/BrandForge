"""Production Orchestrator — two-wave creative production pipeline.

Wave 1 (parallel): Scriptwriter + Mood Board Director + Image Generator
Wave 2 (parallel): Video Producer + Copy Editor (depend on Scriptwriter output)

Uses ADK SequentialAgent with ParallelAgent waves to enforce dependency ordering.
"""

import logging

from google.adk.agents import ParallelAgent, SequentialAgent

from brandforge.agents.copy_editor.agent import copy_editor_agent
from brandforge.agents.image_generator.agent import image_generator_agent
from brandforge.agents.mood_board.agent import mood_board_agent
from brandforge.agents.scriptwriter.agent import scriptwriter_agent
from brandforge.agents.video_producer.agent import video_producer_agent

logger = logging.getLogger(__name__)

# Wave 1: Independent agents that only need Brand DNA
wave_1 = ParallelAgent(
    name="production_wave_1",
    description="Scriptwriter, Mood Board Director, and Image Generator run in parallel.",
    sub_agents=[scriptwriter_agent, mood_board_agent, image_generator_agent],
)

# Wave 2: Agents that depend on Scriptwriter output
wave_2 = ParallelAgent(
    name="production_wave_2",
    description="Video Producer and Copy Editor run in parallel after Scriptwriter completes.",
    sub_agents=[video_producer_agent, copy_editor_agent],
)

# Sequential orchestrator: Wave 1 → Wave 2
production_orchestrator = SequentialAgent(
    name="production_orchestrator",
    description="Two-wave creative production pipeline. Wave 1 generates scripts, mood board, and images. Wave 2 produces videos and refines copy.",
    sub_agents=[wave_1, wave_2],
)

logger.info("Production Orchestrator initialized (wave_1 → wave_2)")
