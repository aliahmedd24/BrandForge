"""Tests for hackathon submission package completeness."""

import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_readme_has_required_sections():
    """README.md must include all required sections for hackathon judges."""
    readme_path = os.path.join(PROJECT_ROOT, "README.md")
    assert os.path.exists(readme_path), "README.md not found at project root"

    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    required_sections = [
        "What It Does",
        "Architecture",
        "Tech Stack",
        "Setup",
        "Demo",
        "Hackathon",
    ]

    for section in required_sections:
        assert section.lower() in content.lower(), (
            f"README.md missing required section: {section}"
        )


def test_architecture_diagram_renders():
    """docs/architecture.md must exist and contain a Mermaid diagram."""
    arch_path = os.path.join(PROJECT_ROOT, "docs", "architecture.md")
    assert os.path.exists(arch_path), "docs/architecture.md not found"

    with open(arch_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "```mermaid" in content, "architecture.md must contain a Mermaid diagram"
    assert "graph" in content.lower(), "Mermaid diagram must contain a graph definition"


def test_demo_video_script_exists():
    """docs/demo-video-script.md must exist."""
    script_path = os.path.join(PROJECT_ROOT, "docs", "demo-video-script.md")
    assert os.path.exists(script_path), "docs/demo-video-script.md not found"

    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert len(content) > 500, "Demo video script seems too short"
