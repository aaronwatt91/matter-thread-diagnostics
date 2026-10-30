"""
Integration tests for FastAPI endpoints in Matter & Thread AI Diagnostics.
"""
import os
import sys
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app

client = TestClient(app)


def test_status_endpoint():
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "ai_provider" in data


def test_collect_diagnostics_endpoint():
    response = client.get("/api/diagnostics/collect")
    assert response.status_code == 200
    data = response.json()
    assert "rule_evaluations" in data
    assert "split_network" in data["rule_evaluations"]
    assert "rf_coexistence" in data["rule_evaluations"]
    assert "topology" in data


def test_topology_endpoint():
    response = client.get("/api/topology")
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data


def test_config_update_endpoint():
    response = client.post("/api/config", json={
        "ai_provider": "gemini",
        "ai_model": "gemini-2.5-flash",
        "gemini_api_key": "AIzaSyTestKey12345",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "updated"
    assert data["config"]["has_gemini_key"] is True
