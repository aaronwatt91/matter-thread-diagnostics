"""
FastAPI application entrypoint for Matter & Thread AI Diagnostics.
Runs inside Home Assistant Green as an Ingress Add-on.
"""
import os
import json
import logging
from datetime import datetime, timezone
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

app = FastAPI(title="Matter & Thread AI Diagnostics", version="1.2.1")

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
    target_thread_network: Optional[str] = None


class SelectThreadNetworkRequest(BaseModel):
    network_id: str


class RunDiagnosisRequest(BaseModel):
    user_notes: Optional[str] = None
    custom_data: Optional[Dict[str, Any]] = None


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
        "target_thread_network": config.target_thread_network,
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
        "target_thread_network": config.target_thread_network,
    }}


@app.get("/api/thread/networks")
async def get_thread_networks():
    """Return all Thread networks available in Home Assistant."""
    networks = await ha_client.get_all_available_thread_networks()
    return {
        "networks": networks,
        "selected_network": config.target_thread_network
    }


@app.post("/api/thread/select_and_scan")
async def select_and_scan_network(req: SelectThreadNetworkRequest):
    """Save selected target Thread network and run full fresh network scan."""
    config.save_options({"target_thread_network": req.network_id})
    telemetry = await gather_full_telemetry()
    return {
        "status": "ok",
        "selected_network": config.target_thread_network,
        "telemetry": telemetry
    }


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
    available_networks = await ha_client.get_all_available_thread_networks()

    # 4. Host Network & IPv6
    ipv6_inspection = await NetworkChecker.inspect_ipv6_routes()
    mdns_info = await NetworkChecker.inspect_mdns_discovery()

    # 5. Extract datasets list
    datasets_list = []
    if isinstance(thread_datasets_res, dict):
        res_data = thread_datasets_res.get("result", {})
        if isinstance(res_data, dict) and "datasets" in res_data:
            d_items = res_data["datasets"]
            datasets_list = d_items if isinstance(d_items, list) else list(d_items.values())
        elif isinstance(res_data, list):
            datasets_list = res_data

    # 6. Extract Thread Border Routers (Nest Wifi Pro, Apple TV, SkyConnect)
    routers_list = []
    if isinstance(thread_routers_res, dict):
        r_data = thread_routers_res.get("result", {})
        if isinstance(r_data, dict) and "routers" in r_data:
            routers_list = r_data["routers"]
        elif isinstance(r_data, list):
            routers_list = r_data

    # 7. Identify active target network & channel
    target_net = None
    target_id = config.target_thread_network
    if target_id:
        for net in available_networks:
            if net.get("id") == target_id or net.get("extended_pan_id") == target_id or net.get("name") == target_id:
                target_net = net
                break

    # Prioritize active channel from selected target network, then dataset, then routers
    active_channel = None
    if target_net and target_net.get("channel"):
        active_channel = target_net["channel"]
    else:
        for d in datasets_list:
            if d.get("channel"):
                active_channel = d.get("channel")
                break
        if not active_channel:
            for r in routers_list:
                if r.get("channel"):
                    active_channel = r.get("channel")
                    break

    # 8. Recent logs
    matter_logs = await ha_client.get_addon_logs("core_matter_server", lines=100)
    otbr_logs = await ha_client.get_addon_logs("core_openthread_border_router", lines=100)

    # 9. Deterministic analysis (integrating target network evaluation)
    rf_analysis = ThreadAnalyzer.analyze_rf_coexistence(active_channel)
    split_net_analysis = ThreadAnalyzer.detect_split_networks(
        routers_list,
        datasets_list,
        device_registry=device_registry,
        target_network_id=target_id
    )
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
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hardware_platform": "Home Assistant Green (Cortex-A55, HAOS)",
        "summary_score": base_score,
        "selected_target_network": target_net,
        "available_thread_networks": available_networks,
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


@app.post("/api/diagnostics/analyze")
async def analyze_diagnostics(req: RunDiagnosisRequest):
    """Run AI diagnosis on live or provided telemetry."""
    if req.custom_data:
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
    Uses strictly 100% real live discovered Border Routers and Matter nodes.
    Highlights nodes that belong to the active target network.
    """
    telemetry = await gather_full_telemetry()
    matter_nodes = telemetry["telemetry"]["matter_server"].get("nodes", [])
    discovered_routers = telemetry["rule_evaluations"]["split_network"].get("all_discovered_routers", [])
    target_net = telemetry.get("selected_target_network")
    target_id = config.target_thread_network
    
    if not discovered_routers and not matter_nodes:
        return {"nodes": [], "edges": [], "target_network": target_net}

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

        is_target_match = True
        status = "online"
        if target_id and target_net:
            target_xpan = (target_net.get("extended_pan_id") or "").upper()
            target_name = (target_net.get("name") or "").lower()
            if target_xpan and target_xpan != "UNKNOWN":
                is_target_match = (r_xpan.upper() == target_xpan)
            else:
                is_target_match = (target_name in r_net.lower() or target_name in r_name.lower())
            if not is_target_match:
                status = "warning"

        target_badge = " [TARGET]" if (target_id and is_target_match) else (" [DESYNCED/SPLIT]" if (target_id and not is_target_match) else "")
        details = f"Model: {r_model} | Brand: {r_brand} | Mesh: {r_net}{target_badge} | PAN: {r_xpan[:8]}... | Ch: {r_ch}"
        graph_nodes.append({
            "id": node_id,
            "label": r_name,
            "type": "border_router",
            "vendor": r_type,
            "status": status,
            "is_target": is_target_match,
            "details": details
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

        # Connect device to nearest border router if available
        if br_node_ids:
            parent_br = br_node_ids[idx % len(br_node_ids)]
            graph_edges.append({
                "source": parent_br,
                "target": f"node_{nid}",
                "label": rssi_str if rssi is not None else "No link",
                "status": "warning" if status in ("offline", "weak") else "ok"
            })

    return {"nodes": graph_nodes, "edges": graph_edges, "target_network": target_net}


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

