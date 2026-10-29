"""
Unit tests for Matter & Thread AI Diagnostic logic and endpoints.
"""
import pytest
import os
import sys

# Ensure app directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from thread_analyzer import ThreadAnalyzer
from ai_engine import AIDiagnosticEngine


def test_rf_coexistence_channel_11_conflict():
    result = ThreadAnalyzer.analyze_rf_coexistence(11, detected_wifi_channels=[1])
    assert result["thread_channel"] == 11
    assert result["severity"] == "HIGH"
    assert result["overlapping_wifi_channel"] == 1
    assert 1 in result["detected_conflicts"]
    assert "Channel 25" in result["recommendation"]


def test_rf_coexistence_channel_25_clean():
    result = ThreadAnalyzer.analyze_rf_coexistence(25, detected_wifi_channels=[1, 6, 11])
    assert result["thread_channel"] == 25
    assert result["severity"] == "MINIMAL"
    assert result["overlapping_wifi_channel"] is None
    assert len(result["detected_conflicts"]) == 0


def test_detect_split_networks_detected():
    routers = [
        {"extended_pan_id": "1111222233334444", "name": "Apple TV 4K", "channel": 15},
        {"extended_pan_id": "AAAABBBBCCCCDDDD", "name": "Home Assistant SkyConnect", "channel": 15}
    ]
    datasets = []
    analysis = ThreadAnalyzer.detect_split_networks(routers, datasets)
    assert analysis["is_split_network"] is True
    assert analysis["distinct_network_count"] == 2
    assert "CRITICAL" in analysis["summary"]


def test_detect_split_networks_synchronized():
    routers = [
        {"extended_pan_id": "1111222233334444", "name": "Apple TV 4K", "channel": 15},
        {"extended_pan_id": "1111222233334444", "name": "Home Assistant SkyConnect", "channel": 15}
    ]
    datasets = [{"extended_pan_id": "1111222233334444", "network_name": "MyMesh"}]
    analysis = ThreadAnalyzer.detect_split_networks(routers, datasets)
    assert analysis["is_split_network"] is False
    assert analysis["distinct_network_count"] == 1
    assert "healthy" in analysis["recommendation"].lower()


def test_evaluate_node_link_quality():
    nodes = [
        {"node_id": 1, "product_name": "Eve Plug", "available": True, "rssi": -60},
        {"node_id": 2, "product_name": "Aqara Contact P2", "available": True, "rssi": -86}, # Weak
        {"node_id": 3, "product_name": "Eve Motion", "available": False, "rssi": None}       # Offline
    ]
    result = ThreadAnalyzer.evaluate_node_link_quality(nodes)
    assert result["total_nodes"] == 3
    assert result["healthy_count"] == 1
    assert result["weak_count"] == 1
    assert result["offline_count"] == 1
    assert len(result["weak_nodes"]) == 1
    assert len(result["offline_nodes"]) == 1
    assert result["health_score"] < 80


def test_ai_diagnostic_engine_key_validation():
    # Gemini valid key check
    engine_gemini = AIDiagnosticEngine(provider="gemini", gemini_key="AIzaSyDummyKeyTest")
    assert engine_gemini.has_valid_key() is True

    # OpenAI missing key check
    engine_openai = AIDiagnosticEngine(provider="openai", openai_key="")
    assert engine_openai.has_valid_key() is False

    # Anthropic valid key check
    engine_claude = AIDiagnosticEngine(provider="anthropic", anthropic_key="sk-ant-validtestkey")
    assert engine_claude.has_valid_key() is True
