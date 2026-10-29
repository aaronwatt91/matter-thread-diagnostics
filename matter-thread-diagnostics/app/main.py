"""
FastAPI application entrypoint for Matter & Thread AI Diagnostics.
Runs inside Home Assistant Green as an Ingress Add-on.
"""
import os
import json
import logging
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import config
from ha_client import HAClient
from matter_client import MatterClient
from thread_analyzer import ThreadAnalyzer
from network_checker import NetworkChecker
from ai_engine import AIDiagnosticEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("matter_thread_ai.main")

app = FastAPI(title="Matter & Thread AI Diagnostics", version="1.0.0")

# Setup clients
ha_client = HAClient(
    supervisor_token=config.supervisor_token,
    ha_url=config.ha_url,
    supervisor_url=config.supervisor_url
)
matter_client = MatterClient(ws_url=config.matter_server_url)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ConfigUpdateRequest(BaseModel):
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    matter_server_url: Optional[str] = None
    otbr_url: Optional[str] = None


class RunDiagnosisRequest(BaseModel):
    user_notes: Optional[str] = None
    custom_data: Optional[Dict[str, Any]] = None
    force_mock: Optional[bool] = False


class ManualLogAnalysisRequest(BaseModel):
    log_content: str
    user_notes: Optional[str] = None


@app.get("/api/status")
async def get_status():
    """Return runtime status of the diagnostics add-on."""
    return {
        "status": "online",
        "running_in_haos": ha_client.is_available,
        "ai_provider": config.ai_provider,
        "ai_model": config.ai_model,
        "has_gemini_key": bool(config.gemini_api_key and len(config.gemini_api_key) > 5),
        "has_openai_key": bool(config.openai_api_key and len(config.openai_api_key) > 5),
        "has_anthropic_key": bool(config.anthropic_api_key and len(config.anthropic_api_key) > 5),
        "matter_server_url": config.matter_server_url,
        "otbr_url": config.otbr_url,
    }


@app.post("/api/config")
async def update_config(req: ConfigUpdateRequest):
    """Update API keys or configuration options."""
    updates = req.model_dump(exclude_unset=True)
    config.save_options(updates)
    return {"status": "updated", "config": {
        "ai_provider": config.ai_provider,
        "ai_model": config.ai_model,
        "has_gemini_key": bool(config.gemini_api_key),
        "has_openai_key": bool(config.openai_api_key),
        "has_anthropic_key": bool(config.anthropic_api_key),
    }}


@app.get("/api/diagnostics/collect")
async def collect_diagnostics():
    """
    Gather complete telemetry from Home Assistant, Matter Server,
    OTBR, host network routing tables, and apply deterministic rules.
    """
    return await gather_full_telemetry()


async def gather_full_telemetry() -> Dict[str, Any]:
    # 1. Matter Server nodes
    matter_info = await matter_client.get_nodes_and_server_info()
    
    # 2. HA Entities
    ha_matter_entities = await ha_client.get_matter_nodes_via_ha()

    # 3. Thread Datasets & Routers from HA
    thread_datasets_res = await ha_client.get_thread_datasets()
    thread_routers_res = await ha_client.get_thread_routers()

    # 4. Host Network & IPv6
    ipv6_inspection = await NetworkChecker.inspect_ipv6_routes()
    mdns_info = await NetworkChecker.inspect_mdns_discovery()

    # 5. Extract active thread channel from dataset or default
    active_channel = None
    datasets_list = []
    if isinstance(thread_datasets_res, dict) and "result" in thread_datasets_res:
        ds_data = thread_datasets_res["result"]
        if isinstance(ds_data, dict) and "datasets" in ds_data:
            datasets_list = ds_data["datasets"]
            for d in datasets_list:
                if d.get("channel"):
                    active_channel = d.get("channel")
                    break

    # 6. Thread Border Routers
    routers_list = []
    if isinstance(thread_routers_res, dict) and "result" in thread_routers_res:
        r_data = thread_routers_res["result"]
        if isinstance(r_data, dict) and "routers" in r_data:
            routers_list = r_data["routers"]
        elif isinstance(r_data, list):
            routers_list = r_data

    # 7. Recent logs
    matter_logs = await ha_client.get_addon_logs("core_matter_server", lines=100)
    otbr_logs = await ha_client.get_addon_logs("core_openthread_border_router", lines=100)

    # 8. Deterministic analysis
    rf_analysis = ThreadAnalyzer.analyze_rf_coexistence(active_channel)
    split_net_analysis = ThreadAnalyzer.detect_split_networks(routers_list, datasets_list)
    node_quality = ThreadAnalyzer.evaluate_node_link_quality(matter_info.get("nodes", []))

    # Calculate overall pre-heuristic health score (0-100)
    base_score = node_quality.get("health_score", 100)
    if split_net_analysis.get("is_split_network"):
        base_score = min(base_score, 40)
    if not ipv6_inspection.get("has_thread_ula_route") and ha_client.is_available:
        base_score = min(base_score, 50)
    if rf_analysis.get("severity") == "HIGH":
        base_score = max(0, base_score - 20)

    return {
        "timestamp": os.environ.get("MOCK_TIME", "2026-10-29T21:51:00Z"),
        "hardware_platform": "Home Assistant Green (Cortex-A55, HAOS)",
        "summary_score": base_score,
        "rule_evaluations": {
            "split_network": split_net_analysis,
            "rf_coexistence": rf_analysis,
            "node_quality": node_quality,
            "ipv6_routing": ipv6_inspection,
        },
        "telemetry": {
            "matter_server": matter_info,
            "ha_matter_entities_count": len(ha_matter_entities),
            "thread_channel": active_channel,
            "border_routers_count": len(routers_list),
            "datasets_count": len(datasets_list),
            "mdns_info": mdns_info,
            "logs_sample": {
                "matter_server_has_logs": bool(matter_logs),
                "matter_server_recent_error_count": matter_logs.lower().count("error"),
                "otbr_has_logs": bool(otbr_logs),
            }
        }
    }


@app.get("/api/mock/sample")
async def get_mock_sample():
    """Return a realistic multi-device Matter-over-Thread diagnostic scenario."""
    return get_sample_telemetry()


@app.post("/api/diagnostics/analyze")
async def analyze_diagnostics(req: RunDiagnosisRequest):
    """Run AI diagnosis on live or provided telemetry."""
    if req.force_mock:
        telemetry_data = get_sample_telemetry()
    elif req.custom_data:
        telemetry_data = req.custom_data
    else:
        telemetry_data = await gather_full_telemetry()

    engine = AIDiagnosticEngine(
        provider=config.ai_provider,
        model=config.ai_model,
        gemini_key=config.gemini_api_key,
        openai_key=config.openai_api_key,
        anthropic_key=config.anthropic_api_key
    )

    ai_result = await engine.run_diagnosis(telemetry_data, user_notes=req.user_notes)
    
    return {
        "telemetry": telemetry_data,
        "ai_result": ai_result
    }


@app.post("/api/manual/analyze")
async def analyze_manual_logs(req: ManualLogAnalysisRequest):
    """Analyze raw logs or user-pasted Thread/Matter diagnostics using AI."""
    engine = AIDiagnosticEngine(
        provider=config.ai_provider,
        model=config.ai_model,
        gemini_key=config.gemini_api_key,
        openai_key=config.openai_api_key,
        anthropic_key=config.anthropic_api_key
    )

    payload = {
        "source": "Manual Diagnostic Log Paste",
        "raw_text": req.log_content
    }

    ai_result = await engine.run_diagnosis(payload, user_notes=req.user_notes)
    return {"ai_result": ai_result}


@app.get("/api/topology")
async def get_topology():
    """Return graph data (nodes & edges) for the interactive mesh visualization."""
    # Attempt live, fallback to sample topology if no live nodes yet
    telemetry = await gather_full_telemetry()
    nodes = telemetry["telemetry"]["matter_server"].get("nodes", [])
    
    if not nodes:
        # Use illustrative topology for visualization
        sample = get_sample_telemetry()
        nodes = sample["telemetry"]["matter_server"]["nodes"]
        border_routers = sample["rule_evaluations"]["split_network"]["networks"]
    else:
        border_routers = telemetry["rule_evaluations"]["split_network"]["networks"]

    graph_nodes = []
    graph_edges = []

    # Border Router root
    graph_nodes.append({
        "id": "br_ha_skyconnect",
        "label": "HA Green (SkyConnect/ZBT-1)",
        "type": "border_router",
        "status": "online",
        "details": "Channel 15, Leader Router"
    })

    # Optional 2nd Border Router
    graph_nodes.append({
        "id": "br_apple_tv",
        "label": "Apple TV 4K",
        "type": "border_router",
        "status": "online",
        "details": "Secondary Thread Border Router"
    })
    graph_edges.append({
        "source": "br_ha_skyconnect",
        "target": "br_apple_tv",
        "label": "Thread Backbone (Link: OK)",
        "status": "ok"
    })

    # Device nodes
    for idx, n in enumerate(nodes):
        nid = str(n.get("node_id"))
        pname = n.get("product_name", f"Node {nid}")
        avail = n.get("available", False)
        is_weak = (n.get("rssi") is not None and n.get("rssi") < -82)

        status = "online" if avail else "offline"
        if avail and is_weak:
            status = "weak"

        node_type = "end_device" if "sensor" in pname.lower() or "contact" in pname.lower() or "motion" in pname.lower() else "router"

        graph_nodes.append({
            "id": f"node_{nid}",
            "label": pname,
            "type": node_type,
            "status": status,
            "details": f"Vendor: {n.get('vendor_name')}, RSSI: {n.get('rssi', -70)} dBm"
        })

        # Connect to a parent
        target = "br_ha_skyconnect" if idx % 2 == 0 else "br_apple_tv"
        graph_edges.append({
            "source": target,
            "target": f"node_{nid}",
            "label": f"{n.get('rssi', -70)} dBm",
            "status": "warning" if status in ("offline", "weak") else "ok"
        })

    return {"nodes": graph_nodes, "edges": graph_edges}


@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    """Serve the Ingress-compatible Single Page Application."""
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            html = f.read()
        return HTMLResponse(content=html)
    return HTMLResponse("<h2>Matter & Thread AI Diagnostics is initializing...</h2>")


def get_sample_telemetry() -> Dict[str, Any]:
    """Provides a realistic Matter-over-Thread diagnostic dump representing common issues."""
    return {
        "timestamp": "2026-10-29T21:50:00Z",
        "hardware_platform": "Home Assistant Green (HAOS 13.x, Cortex-A55)",
        "summary_score": 45,
        "rule_evaluations": {
            "split_network": {
                "is_split_network": True,
                "distinct_network_count": 2,
                "summary": "CRITICAL: Found 2 independent Thread networks with different Extended PAN IDs! Apple TV 4K and Home Assistant SkyConnect have not synchronized credentials.",
                "recommendation": "Import Apple Thread credentials into Home Assistant to unify the Thread mesh.",
                "networks": {
                    "1111222233334444": [{"name": "HomeAssistant-Thread-Mesh", "channel": 15, "pan_id": "0x1234"}],
                    "AAAABBBBCCCCDDDD": [{"name": "MyHome-Apple-Mesh", "channel": 15, "pan_id": "0x5678"}]
                }
            },
            "rf_coexistence": {
                "thread_channel": 11,
                "severity": "HIGH",
                "overlapping_wifi_channel": 1,
                "interference_description": "Wi-Fi Ch 1 direct overlap",
                "recommendation": "Thread Channel 11 has HIGH overlap with 2.4GHz Wi-Fi Channel 1. Change Thread channel to 25."
            },
            "node_quality": {
                "total_nodes": 4,
                "healthy_count": 2,
                "weak_count": 1,
                "offline_count": 1,
                "health_score": 50,
                "summary": "2/4 nodes operational. 1 offline, 1 weak.",
                "offline_nodes": [{"node_id": 14, "name": "Eve Door & Window", "vendor": "Eve Systems", "reason": "Unreachable / Ping Timeout"}],
                "weak_nodes": [{"node_id": 8, "name": "Aqara Door and Window Sensor P2", "vendor": "Lumi United", "rssi": -88, "reason": "Severe RF attenuation (-88 dBm < -82 dBm)"}]
            },
            "ipv6_routing": {
                "has_thread_ula_route": False,
                "status": "WARNING",
                "summary": "CRITICAL WARNING: No IPv6 route to Thread ULA prefix (fd00::/8) found on this host! Check Wi-Fi router Multicast & ICMPv6 RA settings."
            }
        },
        "telemetry": {
            "matter_server": {
                "connected": True,
                "server_version": "6.6.0",
                "nodes": [
                    {"node_id": 2, "product_name": "Eve Energy Smart Plug", "vendor_name": "Eve Systems", "available": True, "transport": "thread", "rssi": -62},
                    {"node_id": 5, "product_name": "Nanoleaf Essentials A19 Bulb", "vendor_name": "Nanoleaf", "available": True, "transport": "thread", "rssi": -69},
                    {"node_id": 8, "product_name": "Aqara Door and Window Sensor P2", "vendor_name": "Lumi United", "available": True, "transport": "thread", "rssi": -88},
                    {"node_id": 14, "product_name": "Eve Door & Window", "vendor_name": "Eve Systems", "available": False, "transport": "thread", "rssi": None}
                ]
            },
            "ha_matter_entities_count": 12,
            "thread_channel": 11,
            "border_routers_count": 2,
            "datasets_count": 2
        }
    }
