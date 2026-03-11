"""Tests for the infrastructure status panel endpoint."""

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_infra_status_returns_services():
    """GET /infra/status returns at least 4 services with LIVE status."""
    from fastapi.testclient import TestClient
    from brandforge.api import app

    client = TestClient(app)
    response = client.get("/infra/status")

    assert response.status_code == 200
    data = response.json()
    assert "project_id" in data
    assert "services" in data
    assert len(data["services"]) >= 4

    for svc in data["services"]:
        assert "name" in svc
        assert "status" in svc
        assert svc["status"] == "LIVE"


@pytest.mark.asyncio
async def test_infra_status_includes_core_services():
    """Verify core GCP services are listed in the status response."""
    from fastapi.testclient import TestClient
    from brandforge.api import app

    client = TestClient(app)
    response = client.get("/infra/status")
    data = response.json()

    service_names = [s["name"] for s in data["services"]]
    assert "Cloud Run" in service_names
    assert "Firestore" in service_names
    assert "Cloud Storage" in service_names
    assert "Vertex AI (Gemini)" in service_names
