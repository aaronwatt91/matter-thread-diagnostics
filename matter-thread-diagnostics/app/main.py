"""
FastAPI application entrypoint for Matter & Thread AI Diagnostics.
Runs inside Home Assistant OS as an Ingress Add-on.
Performs real mDNS (_meshcop._udp, _matter._tcp) discovery, HA Thread dataset TLV decoding,
Matter Cluster 0x0035 (NeighborTable, RouteTable, RSSI/LQI, RLOC16) inspection,
OTBR REST API querying, and active ICMPv6 reachability probing.
"""
import asyncio
import json
import os
import re
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import config
from ha_client import HAClient
from matter_client import MatterClient
from thread_analyzer import ThreadAnalyzer
from network_checker import NetworkChecker
from ai_engine import AIDiagnosticEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
# Prevent httpx / httpcore from logging full request URLs at INFO level
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("matter_thread_ai.main")

_SECRET_PATTERNS = [
    (re.compile(r"AIza[0-9A-Za-z\-_]{15,}"), "AIza***REDACTED***"),
    (re.compile(r"sk-[0-9A-Za-z\-_]{15,}"), "sk-***REDACTED***"),
    (re.compile(r"([?&]key=)[^&\s\"']+"), r"\1***REDACTED***"),
]


def _redact_secrets(text: str) -> str:
    """Scrub any API keys or tokens from log strings before storing or exporting."""
    if not text:
        return text
    out = text
    for pat, repl in _SECRET_PATTERNS:
        out = pat.sub(repl, out)
    return out


class _RingBufferLogHandler(logging.Handler):
    """Captures recent add-on logs in memory so users can download a complete diagnostic bundle."""

    def __init__(self, capacity: int = 500):
        super().__init__()
        self.buffer: deque[str] = deque(maxlen=capacity)
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.buffer.append(_redact_secrets(self.format(record)))
        except Exception:
            pass


_log_ring_handler = _RingBufferLogHandler(capacity=500)
logging.getLogger().addHandler(_log_ring_handler)

app = FastAPI(title="Matter & Thread AI Diagnostics", version="2.0.7")


@app.middleware("http")
async def disable_ingress_cache(request: Request, call_next):
    """Prevent Home Assistant Ingress or browser from caching stale JS/HTML/API responses."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


ha_client = HAClient(
    supervisor_token=config.supervisor_token,
    ha_url=config.ha_url,
    supervisor_url=config.supervisor_url,
)
matter_client = MatterClient(ws_url=config.matter_server_url)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_last_telemetry_cache: Optional[Dict[str, Any]] = None
_last_ai_result_cache: Optional[Dict[str, Any]] = None


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
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None


class ManualLogAnalysisRequest(BaseModel):
    log_content: str
    user_notes: Optional[str] = None
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None


def _safe_unwrap(val: Any, default: Any):
    if isinstance(val, Exception) or val is None:
        return default
    return val


@app.get("/api/status")
async def get_status():
    """Return runtime status of the diagnostics add-on."""
    return {
        "status": "online",
        "version": "2.0.1",
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
    """Update API keys, AI provider/model, or configuration options."""
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
    """Discover and return all Thread networks available across HA, mDNS, OTBR, Matter nodes, and Device Registry."""
    raw_results = await asyncio.gather(
        matter_client.get_nodes_and_server_info(timeout=3.5),
        ha_client.get_thread_datasets(),
        ha_client.get_thread_routers(listen_timeout=1.5),
        NetworkChecker.inspect_mdns_discovery(scan_duration=1.5),
        NetworkChecker.inspect_otbr_rest_api(otbr_url=config.otbr_url),
        ha_client.get_device_registry(),
        return_exceptions=True,
    )
    matter_info = _safe_unwrap(raw_results[0], {"nodes": []})
    datasets_res = _safe_unwrap(raw_results[1], {})
    routers_res = _safe_unwrap(raw_results[2], {})
    mdns_info = _safe_unwrap(raw_results[3], {})
    otbr_info = _safe_unwrap(raw_results[4], {})
    device_registry = _safe_unwrap(raw_results[5], [])

    networks = await ha_client.get_all_available_thread_networks(
        otbr_url=config.otbr_url,
        matter_nodes=matter_info.get("nodes", []) if isinstance(matter_info, dict) else [],
        mdns_info=mdns_info if isinstance(mdns_info, dict) else {},
        otbr_info=otbr_info if isinstance(otbr_info, dict) else {},
        datasets_res=datasets_res if isinstance(datasets_res, dict) else {},
        routers_res=routers_res if isinstance(routers_res, dict) else {},
        device_registry=device_registry if isinstance(device_registry, list) else [],
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
    raw = await asyncio.gather(matter_ping_task, icmp_ping_task, return_exceptions=True)
    matter_res = _safe_unwrap(raw[0], {"node_id": req.node_id, "success": False, "error": "Ping error"})
    icmp_res = _safe_unwrap(raw[1], None)
    return {
        "node_id": req.node_id,
        "matter_ping": matter_res,
        "icmpv6_ping": icmp_res,
    }


@app.get("/api/ai/models")
async def get_ai_models():
    """Fetch live available AI models from the configured provider (e.g. Google ModelService.ListModels)."""
    engine = AIDiagnosticEngine(
        provider=config.ai_provider,
        model=config.ai_model,
        gemini_key=config.gemini_api_key,
        openai_key=config.openai_api_key,
        anthropic_key=config.anthropic_api_key,
    )
    models = await engine.list_available_models()
    return {
        "provider": config.ai_provider,
        "selected_model": config.ai_model,
        "models": models,
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

    # 1. Execute all live discovery & telemetry probes concurrently with full fault tolerance
    raw_probe = await asyncio.gather(
        matter_client.get_nodes_and_server_info(timeout=4.5),
        ha_client.get_matter_nodes_via_ha(),
        ha_client.get_thread_datasets(),
        ha_client.get_thread_routers(listen_timeout=1.8),
        ha_client.get_device_registry(),
        NetworkChecker.inspect_mdns_discovery(scan_duration=1.8),
        NetworkChecker.inspect_otbr_rest_api(otbr_url=config.otbr_url),
        NetworkChecker.inspect_ipv6_routes(),
        ha_client.get_addon_logs("core_matter_server", lines=100),
        ha_client.get_addon_logs("core_openthread_border_router", lines=100),
        return_exceptions=True,
    )

    matter_info = _safe_unwrap(raw_probe[0], {"connected": False, "nodes": [], "error": "Probe error"})
    ha_matter_entities = _safe_unwrap(raw_probe[1], [])
    thread_datasets_res = _safe_unwrap(raw_probe[2], {})
    thread_routers_res = _safe_unwrap(raw_probe[3], {})
    device_registry = _safe_unwrap(raw_probe[4], [])
    mdns_info = _safe_unwrap(raw_probe[5], {"mdns_capable": False, "meshcop_border_routers": [], "matter_operational_nodes": []})
    otbr_info = _safe_unwrap(raw_probe[6], {"reachable": False})
    ipv6_inspection = _safe_unwrap(raw_probe[7], {"has_thread_ula_route": False, "detected_ula_prefixes": [], "sample_routes": []})
    matter_logs = _safe_unwrap(raw_probe[8], "")
    otbr_logs = _safe_unwrap(raw_probe[9], "")

    all_matter_nodes: List[Dict[str, Any]] = matter_info.get("nodes", []) if isinstance(matter_info, dict) else []

    # Enrich Matter nodes with IPv6 addresses discovered via mDNS `_matter._tcp.local.`
    mdns_op_by_node_id = {
        m["node_id"]: m
        for m in (mdns_info.get("matter_operational_nodes", []) if isinstance(mdns_info, dict) else [])
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
            n["mdns_hostname"] = mdns_op_by_node_id[nid].get("server")

    # 2. Build normalized list of available Thread networks
    available_networks = await ha_client.get_all_available_thread_networks(
        otbr_url=config.otbr_url,
        matter_nodes=all_matter_nodes,
        mdns_info=mdns_info,
        otbr_info=otbr_info,
        datasets_res=thread_datasets_res,
        routers_res=thread_routers_res,
        device_registry=device_registry,
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

    # 5. Evaluate Border Router synchronization & Split Networks across all sources
    split_net_analysis = ThreadAnalyzer.detect_split_networks(
        routers_list,
        datasets_list,
        device_registry=device_registry,
        target_network_id=target_id,
        mdns_routers=mdns_info.get("meshcop_border_routers", []),
        otbr_info=otbr_info,
    )
    all_routers = split_net_analysis.get("all_discovered_routers", [])

    # 6. Determine active Thread channel
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
        try:
            reachability_probes = await NetworkChecker.probe_network_reachability(all_routers, all_matter_nodes)
        except Exception as e:
            logger.debug("Reachability probe error: %s", e)

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
    # If the user passed a specific provider or model in the request, save & apply it immediately
    updates = {}
    if req.ai_provider:
        updates["ai_provider"] = req.ai_provider
    if req.ai_model:
        updates["ai_model"] = req.ai_model
    if updates:
        config.save_options(updates)

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
    global _last_ai_result_cache
    _last_ai_result_cache = ai_result

    return {
        "telemetry": telemetry_data,
        "ai_result": ai_result,
    }


@app.post("/api/manual/analyze")
async def analyze_manual_logs(req: ManualLogAnalysisRequest):
    """Analyze raw logs or user-pasted Thread/Matter diagnostics using AI."""
    updates = {}
    if req.ai_provider:
        updates["ai_provider"] = req.ai_provider
    if req.ai_model:
        updates["ai_model"] = req.ai_model
    if updates:
        config.save_options(updates)

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
    global _last_ai_result_cache
    _last_ai_result_cache = ai_result
    return {"ai_result": ai_result}


async def _build_diagnostic_log_bundle() -> Dict[str, Any]:
    """Assemble full diagnostic log & telemetry bundle for download."""
    telemetry_data = _last_telemetry_cache
    if telemetry_data is None:
        telemetry_data = await gather_full_telemetry(run_active_pings=False)

    raw_logs = await asyncio.gather(
        ha_client.get_addon_logs("core_matter_server", lines=200),
        ha_client.get_addon_logs("core_openthread_border_router", lines=200),
        return_exceptions=True,
    )
    matter_logs = _safe_unwrap(raw_logs[0], "")
    otbr_logs = _safe_unwrap(raw_logs[1], "")
    addon_internal_logs = "\n".join(_log_ring_handler.buffer)

    now_iso = datetime.now(timezone.utc).isoformat()
    sections = [
        "================================================================================",
        f"MATTER & THREAD AI DIAGNOSTICS — FULL LOG & TELEMETRY BUNDLE",
        f"Generated At: {now_iso}",
        f"Selected Provider / Model: {config.ai_provider} / {config.ai_model}",
        f"Selected Target Network: {config.target_thread_network or 'All Networks'}",
        "================================================================================",
        "",
        "--- [1] ADD-ON INTERNAL APPLICATION LOGS (matter_thread_ai) ---",
        addon_internal_logs or "(No internal application log entries recorded yet)",
        "",
        "--- [2]LATEST AI DIAGNOSTIC REPORT ---",
        (
            f"Model: {_last_ai_result_cache.get('provider')} ({_last_ai_result_cache.get('model')})\n\n"
            + str(_last_ai_result_cache.get("analysis") or _last_ai_result_cache.get("error") or "")
        )
        if _last_ai_result_cache
        else "(No AI diagnostic report run in this session yet)",
        "",
        "--- [3] HOME ASSISTANT MATTER SERVER LOGS (core_matter_server) ---",
        matter_logs or "(No Matter Server logs returned via Supervisor API)",
        "",
        "--- [4] OPENTHREAD BORDER ROUTER LOGS (core_openthread_border_router) ---",
        otbr_logs or "(No OTBR logs returned via Supervisor API)",
        "",
        "--- [5] FULL LIVE NETWORK SCAN TELEMETRY (JSON) ---",
        json.dumps(telemetry_data, indent=2, default=str),
        "",
    ]
    bundle_text = _redact_secrets("\n".join(sections))
    return {
        "timestamp": now_iso,
        "bundle_text": bundle_text,
        "addon_logs": _redact_secrets(addon_internal_logs),
        "matter_server_logs": _redact_secrets(matter_logs),
        "otbr_logs": _redact_secrets(otbr_logs),
    }


@app.get("/api/diagnostics/logs")
async def get_diagnostic_logs():
    """Return full diagnostic log bundle as JSON for browser Blob download or viewing."""
    return await _build_diagnostic_log_bundle()


@app.get("/api/diagnostics/download")
async def download_diagnostic_logs():
    """Direct file download endpoint for diagnostic logs and telemetry."""
    bundle = await _build_diagnostic_log_bundle()
    ts_slug = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"matter-thread-diagnostics-{ts_slug}.log"
    return PlainTextResponse(
        content=bundle["bundle_text"],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
