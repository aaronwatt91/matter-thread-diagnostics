"""
FastAPI application entrypoint for Matter & Thread AI Diagnostics.
Runs inside Home Assistant OS (with host_network: true) as an Ingress Add-on.
Performs real mDNS (_meshcop._udp, _matter._tcp) discovery, HA Thread dataset TLV decoding,
Matter Cluster 0x0035 (NeighborTable, RouteTable, RSSI/LQI, RLOC16) inspection,
OTBR REST API querying, and active ICMPv6 reachability probing.
"""
import asyncio
import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
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

app = FastAPI(title="Matter & Thread AI Diagnostics", version="2.0.0")

ha_client = HAClient(
    supervisor_token=config.supervisor_token,
    ha_url=config.ha_url,
    supervisor_url=config.supervisor_url,
)
matter_client = MatterClient(ws_url=config.matter_server_url)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Cache of the most recent full scan so AI analysis & topology views can reuse fresh scan data immediately
_last_telemetry_cache: Optional[Dict[str, Any]] = None


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
    network_id: str = ""


class PingNodeRequest(BaseModel):
    node_id: int
    ipv6_address: Optional[str] = None


class RunDiagnosisRequest(BaseModel):
    user_notes: Optional[str] = None
    custom_data: Optional[Dict[str, Any]] = None
    use_cached_scan: bool = True


class ManualLogAnalysisRequest(BaseModel):
    log_content: str
    user_notes: Optional[str] = None


@app.get("/api/status")
async def get_status():
    """Return runtime status of the diagnostics add-on."""
    return {
        "status": "online",
        "version": "2.0.0",
        "running_in_haos": ha_client.is_available,
        "ai_provider": config.ai_provider,
        "ai_model": config.ai_model,
        "has_gemini_key": bool(config.gemini_api_key and len(config.gemini_api_key) > 5),
        "has_openai_key": bool(config.openai_api_key and len(config.openai_api_key) > 5),
        "has_anthropic_key": bool(config.anthropic_key if hasattr(config, "anthropic_key") else (config.anthropic_api_key and len(config.anthropic_api_key) > 5)),
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
    matter_client.ws_url = config.matter_server_url
    return {
        "status": "updated",
        "config": {
            "ai_provider": config.ai_provider,
            "ai_model": config.ai_model,
            "has_gemini_key": bool(config.gemini_api_key),
            "has_openai_key": bool(config.openai_api_key),
            "has_anthropic_key": bool(config.anthropic_api_key),
            "target_thread_network": config.target_thread_network,
        },
    }


@app.get("/api/thread/networks")
async def get_thread_networks():
    """Discover and return all real Thread networks available across HA, mDNS, OTBR, and Matter nodes."""
    matter_info, datasets_res, routers_res, mdns_info, otbr_info = await asyncio.gather(
        matter_client.get_nodes_and_server_info(timeout=3.5),
        ha_client.get_thread_datasets(),
        ha_client.get_thread_routers(listen_timeout=1.5),
        NetworkChecker.inspect_mdns_discovery(scan_duration=1.5),
        NetworkChecker.inspect_otbr_rest_api(otbr_url=config.otbr_url),
    )
    networks = await ha_client.get_all_available_thread_networks(
        otbr_url=config.otbr_url,
        matter_nodes=matter_info.get("nodes", []),
        mdns_info=mdns_info,
        otbr_info=otbr_info,
        datasets_res=datasets_res,
        routers_res=routers_res,
    )
    return {
        "networks": networks,
        "selected_network": config.target_thread_network,
    }


@app.post("/api/thread/select_and_scan")
async def select_and_scan_network(req: SelectThreadNetworkRequest):
    """Save selected target Thread network and execute a full live multi-protocol diagnostic scan."""
    config.save_options({"target_thread_network": req.network_id})
    telemetry = await gather_full_telemetry(run_active_pings=True)
    return {
        "status": "ok",
        "selected_network": config.target_thread_network,
        "telemetry": telemetry,
        "topology": telemetry.get("topology"),
    }


@app.post("/api/matter/ping_node")
async def ping_matter_node(req: PingNodeRequest):
    """Actively ping a Matter node via both python-matter-server `ping_node` and ICMPv6 `ping -6`."""
    matter_ping_task = matter_client.ping_node(req.node_id, timeout=8.0)
    icmp_ping_task = (
        NetworkChecker.ping_address(req.ipv6_address, count=3, timeout_sec=1)
        if req.ipv6_address
        else asyncio.sleep(0, result=None)
    )
    matter_res, icmp_res = await asyncio.gather(matter_ping_task, icmp_ping_task)
    return {
        "node_id": req.node_id,
        "matter_ping": matter_res,
        "icmpv6_ping": icmp_res,
    }


@app.post("/api/test_ai")
async def test_ai_connection():
    """Test AI connection and API key."""
    engine = AIDiagnosticEngine(
        provider=config.ai_provider,
        model=config.ai_model,
        gemini_key=config.gemini_api_key,
        openai_key=config.openai_api_key,
        anthropic_key=config.anthropic_api_key,
    )
    return await engine.test_connection()


@app.get("/api/diagnostics/collect")
async def collect_diagnostics():
    """Gather complete live telemetry across Matter Server, HA Thread, mDNS, OTBR, and IPv6 routing."""
    return await gather_full_telemetry(run_active_pings=True)


async def gather_full_telemetry(run_active_pings: bool = True) -> Dict[str, Any]:
    global _last_telemetry_cache

    # 1. Execute all live discovery & telemetry probes concurrently
    (
        matter_info,
        ha_matter_entities,
        thread_datasets_res,
        thread_routers_res,
        mdns_info,
        otbr_info,
        ipv6_inspection,
        matter_logs,
        otbr_logs,
    ) = await asyncio.gather(
        matter_client.get_nodes_and_server_info(timeout=4.5),
        ha_client.get_matter_nodes_via_ha(),
        ha_client.get_thread_datasets(),
        ha_client.get_thread_routers(listen_timeout=1.8),
        NetworkChecker.inspect_mdns_discovery(scan_duration=2.0),
        NetworkChecker.inspect_otbr_rest_api(otbr_url=config.otbr_url),
        NetworkChecker.inspect_ipv6_routes(),
        ha_client.get_addon_logs("core_matter_server", lines=100),
        ha_client.get_addon_logs("core_openthread_border_router", lines=100),
    )

    all_matter_nodes: List[Dict[str, Any]] = matter_info.get("nodes", [])

    # Enrich Matter nodes with IPv6 addresses discovered via mDNS `_matter._tcp.local.` if Cluster 0x0033 didn't report them
    mdns_op_by_node_id = {
        m["node_id"]: m
        for m in mdns_info.get("matter_operational_nodes", [])
        if isinstance(m, dict) and m.get("node_id") is not None
    }
    for n in all_matter_nodes:
        nid = n.get("node_id")
        if nid in mdns_op_by_node_id:
            mdns_v6 = mdns_op_by_node_id[nid].get("ipv6_addresses", [])
            existing_v6 = n.get("ipv6_addresses") or []
            for ip in mdns_v6:
                if ip not in existing_v6:
                    existing_v6.append(ip)
            n["ipv6_addresses"] = existing_v6
            n["mdns_Hostname"] = mdns_op_by_node_id[nid].get("server")

    # 2. Build normalized list of available Thread networks
    available_networks = await ha_client.get_all_available_thread_networks(
        otbr_url=config.otbr_url,
        matter_nodes=all_matter_nodes,
        mdns_info=mdns_info,
        otbr_info=otbr_info,
        datasets_res=thread_datasets_res,
        routers_res=thread_routers_res,
    )

    # 3. Extract raw datasets list & HA routers list
    datasets_list = []
    if isinstance(thread_datasets_res, dict):
        res_data = thread_datasets_res.get("result", {})
        if isinstance(res_data, dict) and "datasets" in res_data:
            d_items = res_data["datasets"]
            datasets_list = d_items if isinstance(d_items, list) else list(d_items.values())
        elif isinstance(res_data, list):
            datasets_list = res_data

    routers_list = []
    if isinstance(thread_routers_res, dict):
        r_data = thread_routers_res.get("result", {})
        if isinstance(r_data, dict) and "routers" in r_data:
            routers_list = r_data["routers"]
        elif isinstance(r_data, list):
            routers_list = r_data

    # 4. Identify selected target Thread network
    target_net = None
    target_id = (config.target_thread_network or "").strip()
    if target_id:
        for net in available_networks:
            if (
                net.get("id") == target_id
                or net.get("extended_pan_id") == target_id
                or net.get("name") == target_id
            ):
                target_net = net
                break

    # 5. Evaluate Border Router synchronization & Split Networks across all real sources
    split_net_analysis = ThreadAnalyzer.detect_split_networks(
        routers_list,
        datasets_list,
        target_network_id=target_id,
        mdns_routers=mdns_info.get("meshcop_border_routers", []),
        otbr_info=otbr_info,
    )
    all_routers = split_net_analysis.get("all_discovered_routers", [])

    # 6. Determine active Thread channel (from selected network -> OTBR -> datasets -> Matter nodes -> routers)
    active_channel = None
    if target_net and target_net.get("channel"):
        active_channel = target_net["channel"]
    elif otbr_info.get("reachable") and otbr_info.get("channel"):
        active_channel = otbr_info["channel"]
    else:
        for d in datasets_list:
            if isinstance(d, dict) and d.get("channel"):
                active_channel = d["channel"]
                break
        if not active_channel:
            for n in all_matter_nodes:
                if n.get("thread_channel"):
                    active_channel = n["thread_channel"]
                    break
        if not active_channel:
            for r in all_routers:
                if r.get("channel"):
                    active_channel = r["channel"]
                    break

    # 7. Run active ICMPv6/ICMPv4 reachability pings to Border Routers & Matter nodes
    reachability_probes = {"probed_count": 0, "reachable_count": 0, "results": []}
    if run_active_pings and (all_routers or all_matter_nodes):
        reachability_probes = await NetworkChecker.probe_network_reachability(all_routers, all_matter_nodes)

    # 8. Deterministic RF & Node Quality analysis
    rf_analysis = ThreadAnalyzer.analyze_rf_coexistence(active_channel)
    node_quality = ThreadAnalyzer.evaluate_node_link_quality(all_matter_nodes, target_network_id=target_id)

    # 9. Build real topology graph
    topology_data = ThreadAnalyzer.build_real_mesh_topology(
        discovered_routers=all_routers,
        matter_nodes=all_matter_nodes,
        target_net=target_net,
        target_id=target_id,
        is_split=split_net_analysis.get("is_split_network", False),
        ping_results=reachability_probes.get("results", []),
    )

    # 10. Calculate overall health score (0-100)
    base_score = node_quality.get("health_score", 100)
    if split_net_analysis.get("is_split_network"):
        base_score = min(base_score, 45)
    if not ipv6_inspection.get("has_thread_ula_route") and (all_routers or all_matter_nodes):
        base_score = min(base_score, 55)
    if rf_analysis.get("severity") == "HIGH":
        base_score = max(0, base_score - 15)
    if node_quality.get("wrong_network_count", 0) > 0:
        base_score = max(0, base_score - 15)

    # Extract recent error lines from Matter Server and OTBR logs for quick inspection
    matter_error_lines = [
        line for line in (matter_logs or "").splitlines()
        if any(w in line.lower() for w in ("error", "warning", "timeout", "failed", "unreachable", "chip_error"))
    ][-15:]
    otbr_error_lines = [
        line for line in (otbr_logs or "").splitlines()
        if any(w in line.lower() for w in ("error", "warn", "fail", "detached"))
    ][-15:]

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hardware_platform": "Home Assistant OS (Host Network Mode)",
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
            "datasets": datasets_list,
            "otbr": otbr_info,
            "mdns_info": mdns_info,
            "reachability_probes": reachability_probes,
            "logs_sample": {
                "matter_server_has_logs": bool(matter_logs),
                "matter_server_recent_error_count": (matter_logs or "").lower().count("error"),
                "matter_server_recent_errors": matter_error_lines,
                "otbr_has_logs": bool(otbr_logs),
                "otbr_recent_errors": otbr_error_lines,
            },
        },
        "topology": topology_data,
    }

    _last_telemetry_cache = payload
    return payload


@app.post("/api/diagnostics/analyze")
async def analyze_diagnostics(req: RunDiagnosisRequest):
    """Run AI diagnosis on the scanned telemetry (or collect fresh telemetry if none cached)."""
    if req.custom_data:
        telemetry_data = req.custom_data
    elif req.use_cached_scan and _last_telemetry_cache is not None:
        telemetry_data = _last_telemetry_cache
    else:
        telemetry_data = await gather_full_telemetry(run_active_pings=True)

    engine = AIDiagnosticEngine(
        provider=config.ai_provider,
        model=config.ai_model,
        gemini_key=config.gemini_api_key,
        openai_key=config.openai_api_key,
        anthropic_key=config.anthropic_api_key,
    )

    ai_result = await engine.run_diagnosis(telemetry_data, user_notes=req.user_notes)

    return {
        "telemetry": telemetry_data,
        "ai_result": ai_result,
    }


@app.post("/api/manual/analyze")
async def analyze_manual_logs(req: ManualLogAnalysisRequest):
    """Analyze raw logs or user-pasted Thread/Matter diagnostics using AI."""
    engine = AIDiagnosticEngine(
        provider=config.ai_provider,
        model=config.ai_model,
        gemini_key=config.gemini_api_key,
        openai_key=config.openai_api_key,
        anthropic_key=config.anthropic_api_key,
    )

    payload = {
        "source": "Manual Diagnostic Log Paste",
        "raw_text": req.log_content,
    }

    ai_result = await engine.run_diagnosis(payload, user_notes=req.user_notes)
    return {"ai_result": ai_result}


@app.get("/api/topology")
async def get_topology():
    """Return dynamic graph data (nodes & edges) for the interactive mesh visualization."""
    telemetry = await gather_full_telemetry(run_active_pings=True)
    return telemetry.get("topology", {"nodes": [], "edges": [], "target_network": None})


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
