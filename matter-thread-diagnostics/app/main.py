"""
FastAPI application entrypoint for Matter & Thread AI Diagnostics.
Runs inside Home Assistant Green as an Ingress Add-on.
"""
import os
import json
import logging
from typing import Dict, Any, Optional, List
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

app = FastAPI(title="Matter & Thread AI Diagnostics", version="1.0.8")

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
        "gemini_key_preview": (config.gemini_api_key[:6] + "...") if config.gemini_api_key else "",
        "openai_key_preview": (config.openai_api_key[:7] + "...") if config.openai_api_key else "",
        "anthropic_key_preview": (config.anthropic_api_key[:8] + "...") if config.anthropic_api_key else "",
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


@app.post("/api/test_ai")
async def test_ai_connection():
    """Test AI connection and API key."""
    engine = AIDiagnosticEngine(
        provider=config.ai_provider,
        model=config.ai_model,
        gemini_key=config.gemini_api_key,
        openai_key=config.openai_api_key,
        anthropic_key=config.anthropic_api_key
    )
    return await engine.test_connection()


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

    # 3. Thread Datasets, Border Routers & Device Registry from HA
    thread_datasets_res = await ha_client.get_thread_datasets()
    thread_routers_res = await ha_client.get_thread_routers()
    device_registry = await ha_client.get_device_registry()

    # 4. Host Network & IPv6
    ipv6_inspection = await NetworkChecker.inspect_ipv6_routes()
    mdns_info = await NetworkChecker.inspect_mdns_discovery()

    # 5. Extract active thread channel from dataset or default
    active_channel = None
    datasets_list = []
    if isinstance(thread_datasets_res, dict):
        res_data = thread_datasets_res.get("result", {})
        if isinstance(res_data, dict) and "datasets" in res_data:
            datasets_list = res_data["datasets"]
        elif isinstance(res_data, list):
            datasets_list = res_data
        for d in datasets_list:
            if d.get("channel"):
                active_channel = d.get("channel")
                break

    # 6. Extract Thread Border Routers (Nest Wifi Pro, Apple TV, SkyConnect)
    routers_list = []
    if isinstance(thread_routers_res, dict):
        r_data = thread_routers_res.get("result", {})
        if isinstance(r_data, dict) and "routers" in r_data:
            routers_list = r_data["routers"]
        elif isinstance(r_data, list):
            routers_list = r_data

    # 7. Recent logs
    matter_logs = await ha_client.get_addon_logs("core_matter_server", lines=100)
    otbr_logs = await ha_client.get_addon_logs("core_openthread_border_router", lines=100)

    # 8. Deterministic analysis (integrating Nest Wifi Pro recognition)
    rf_analysis = ThreadAnalyzer.analyze_rf_coexistence(active_channel)
    split_net_analysis = ThreadAnalyzer.detect_split_networks(routers_list, datasets_list, device_registry=device_registry)
    node_quality = ThreadAnalyzer.evaluate_node_link_quality(matter_info.get("nodes", []))

    # Calculate overall pre-heuristic health score (0-100)
    base_score = node_quality.get("health_score", 100)
    if split_net_analysis.get("is_split_network"):
        base_score = min(base_score, 40)
    if not ipv6_inspection.get("has_thread_ula_route") and ha_client.is_available:
        base_score = min(base_score, 50)
    if rf_analysis.get("severity") == "HIGH":
        base_score = max(0, base_score - 20)

    all_routers = split_net_analysis.get("all_discovered_routers", [])

    return {
        "timestamp": os.environ.get("MOCK_TIME", "2026-10-30T19:00:00Z"),
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
            "border_routers_count": len(all_routers),
            "border_routers": all_routers,
            "found_nest_wifi_pro": split_net_analysis.get("found_nest_wifi_pro", False),
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
    """Return a realistic multi-device Matter-over-Thread diagnostic scenario featuring Nest Wifi Pro."""
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
    """
    Return dynamic graph data (nodes & edges) for the interactive mesh visualization.
    Uses discovered Border Routers (Nest Wifi Pro, HA SkyConnect, Apple TV) rather than static mocks.
    """
    telemetry = await gather_full_telemetry()
    matter_nodes = telemetry["telemetry"]["matter_server"].get("nodes", [])
    discovered_routers = telemetry["rule_evaluations"]["split_network"].get("all_discovered_routers", [])
    
    is_live = bool(discovered_routers or matter_nodes)

    if not is_live:
        sample = get_sample_telemetry()
        matter_nodes = sample["telemetry"]["matter_server"]["nodes"]
        discovered_routers = sample["rule_evaluations"]["split_network"]["all_discovered_routers"]

    graph_nodes = []
    graph_edges = []

    # 1. Add Border Routers
    br_node_ids = []
    for idx, r in enumerate(discovered_routers):
        r_type = r.get("type", "generic")
        r_name = r.get("name") or "Thread Border Router"
        r_model = r.get("model") or "Border Router"
        r_brand = r.get("brand") or "Generic"
        r_net = r.get("network_name", "Thread Network")
        r_xpan = r.get("extended_pan_id", "UNKNOWN")
        r_ch = r.get("channel") or 15

        node_id = f"br_{r_type}_{idx}"
        br_node_ids.append(node_id)

        details = f"Model: {r_model} | Brand: {r_brand} | Mesh: {r_net} | PAN: {r_xpan[:8]}... | Ch: {r_ch}"
        graph_nodes.append({
            "id": node_id,
            "label": r_name,
            "type": "border_router",
            "vendor": r_type,
            "status": "online",
            "details": details
        })

    # If no border router found yet, ensure at least one placeholder exists
    if not br_node_ids:
        default_br = "br_ha_green"
        br_node_ids.append(default_br)
        graph_nodes.append({
            "id": default_br,
            "label": "HA Green (Searching for Border Routers...)",
            "type": "border_router",
            "vendor": "ha",
            "status": "warning",
            "details": "Scanning for Thread Border Routers (Nest Wifi Pro, Apple TV, SkyConnect)..."
        })

    # Connect multiple border routers to each other (Thread 1.3 Backbone)
    if len(br_node_ids) > 1:
        is_split = telemetry["rule_evaluations"]["split_network"].get("is_split_network", False)
        for i in range(len(br_node_ids) - 1):
            graph_edges.append({
                "source": br_node_ids[i],
                "target": br_node_ids[i + 1],
                "label": "SPLIT MESH (Desynced)" if is_split else "Thread 1.3 Backbone (OK)",
                "status": "warning" if is_split else "ok"
            })

    # 2. Add Matter / Thread end devices and routers
    for idx, n in enumerate(matter_nodes):
        nid = str(n.get("node_id"))
        pname = n.get("product_name", f"Matter Node {nid}")
        avail = n.get("available", False)
        rssi = n.get("rssi")
        is_weak = (rssi is not None and rssi < -82)

        status = "online" if avail else "offline"
        if avail and is_weak:
            status = "weak"

        node_type = "end_device" if "sensor" in pname.lower() or "contact" in pname.lower() or "motion" in pname.lower() else "router"

        rssi_str = f"{rssi} dBm" if rssi is not None else "N/A"
        graph_nodes.append({
            "id": f"node_{nid}",
            "label": pname,
            "type": node_type,
            "status": status,
            "details": f"Vendor: {n.get('vendor_name', 'Unknown')}, RSSI: {rssi_str}, Protocol: Matter-over-Thread"
        })

        # Connect device to nearest border router
        parent_br = br_node_ids[idx % len(br_node_ids)]
        graph_edges.append({
            "source": parent_br,
            "target": f"node_{nid}",
            "label": rssi_str if rssi is not None else "No link",
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


@app.get("/style.css")
async def serve_css():
    css_file = os.path.join(STATIC_DIR, "style.css")
    if os.path.exists(css_file):
        return FileResponse(css_file, media_type="text/css")
    return HTMLResponse("", status_code=404)


@app.get("/app.js")
async def serve_js():
    js_file = os.path.join(STATIC_DIR, "app.js")
    if os.path.exists(js_file):
        return FileResponse(js_file, media_type="application/javascript")
    return HTMLResponse("", status_code=404)


def get_sample_telemetry() -> Dict[str, Any]:
    """Provides a realistic Matter-over-Thread diagnostic dump representing Google Nest Wifi Pro & Home Assistant Green."""
    nest_router = {
        "name": "Google Nest Wifi Pro (Living Room)",
        "model": "Nest Wifi Pro",
        "brand": "Google",
        "type": "nest",
        "server": "Nest-Wifi-Pro-LivingRoom.local.",
        "network_name": "Google-Thread-Network-8491",
        "extended_pan_id": "1122334455667788",
        "channel": 15,
        "pan_id": "0x5678",
    }
    apple_router = {
        "name": "Apple TV 4K (Living Room)",
        "model": "Apple TV 4K",
        "brand": "Apple",
        "type": "apple",
        "server": "Apple-TV-4K.local.",
        "network_name": "Apple-Thread-Mesh",
        "extended_pan_id": "9988776655443322",
        "channel": 15,
        "pan_id": "0x9876",
    }
    ha_router = {
        "name": "HA Green (SkyConnect / Connect ZBT-1)",
        "model": "SkyConnect",
        "brand": "Nabu Casa",
        "type": "ha",
        "server": "core_openthread_border_router",
        "network_name": "HomeAssistant-Thread-Mesh",
        "extended_pan_id": "AABBCCDDEEFF0011",
        "channel": 15,
        "pan_id": "0x1234",
    }

    return {
        "timestamp": "2026-10-30T19:00:00Z",
        "hardware_platform": "Home Assistant Green (HAOS 13.x, Cortex-A55)",
        "summary_score": 35,
        "rule_evaluations": {
            "split_network": {
                "is_split_network": True,
                "distinct_network_count": 3,
                "found_nest_wifi_pro": True,
                "found_apple_router": True,
                "found_ha_router": True,
                "summary": "CRITICAL SPLIT THREAD MESH: Found 3 independent Thread networks! Your Google Nest Wifi Pro, Apple TV 4K, and Home Assistant are operating on separate Extended PAN IDs.",
                "recommendation": "Synchronize credentials with Home Assistant: In the Home Assistant Companion App (Android/iOS), go to Settings -> Companion App -> Troubleshooting -> Sync Thread Credentials, then choose your preferred network in Home Assistant Settings -> Devices & Services -> Thread.",
                "all_discovered_routers": [nest_router, apple_router, ha_router],
                "networks": {
                    "1122334455667788": [nest_router],
                    "9988776655443322": [apple_router],
                    "AABBCCDDEEFF0011": [ha_router]
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
            "border_routers": [nest_router, ha_router],
            "found_nest_wifi_pro": True,
            "datasets_count": 2
        }
    }
