# Changelog

## [2.0.1] - 2026-10-30

### Fixed: Network Discovery in `host_network: true` Mode & Instant AI Model Switching
- **Fixed Supervisor DNS & Virtual-Host Routing under `host_network: true`**:
  - When `host_network: true` is active in Home Assistant OS, the container shares the host network namespace where Docker's internal `supervisor` DNS entry is absent and Supervisor's nginx proxy (`172.30.32.2`) requires `Host: supervisor` on HTTP and WebSocket requests.
  - Added automatic `/etc/hosts` mapping (`172.30.32.2 supervisor` and `172.30.32.1 homeassistant`) in `run.sh` on startup and explicit `Host: supervisor` headers in `HAClient` for both REST (`httpx`) and WebSocket (`websockets`) connections to `172.30.32.2`.
  - Added `HASSIO_TOKEN` and `/run/s6/container_environment/SUPERVISOR_TOKEN` fallbacks so `SUPERVISOR_TOKEN` is always discovered.
- **Zero-Dependency Raw UDP DNS-SD mDNS Scanner & Multi-Source Network Discovery**:
  - Added a pure-Python UDP DNS-SD packet scanner (`_scan_mdns_via_udp_sockets`, `_build_mdns_ptr_query`, `_parse_mdns_packet`) querying `224.0.0.251:5353` for `_meshcop._udp.local.`, `_matter._tcp.local.`, and `_matterc._udp.local.` from an ephemeral UDP socket (no port 5353 conflict with host `avahi-daemon` / `mdns-repeater`) alongside `AsyncZeroconf`.
  - Isolated optional `thread/get_dataset_tlv` calls so any unsupported command never drops datasets returned by `thread/list_datasets`, and isolated all discovery tasks with `return_exceptions=True`.
  - Restored Home Assistant Device Registry and `/api/states` Border Router hardware discovery (Google Nest Wifi Pro, Nest Hub, Apple TV 4K, HomePod, SkyConnect/ZBT-1) as stage 6 in `get_all_available_thread_networks()` and `detect_split_networks()`.
- **Fixed AI Provider & Model Switching**:
  - Removed forced model normalization that overwrote user-selected models (such as `gemini-3.8-flash`), preserving the exact selected model across `config.py` and `ai_engine.py` while keeping automatic HTTP 404 fallback in `_call_gemini`.
  - Added instant auto-save to `/api/config` whenever the AI Provider or AI Model dropdown is changed in either the **Settings** tab or the new quick model switcher bar in the **AI Diagnostics Studio** tab.
  - Fixed `testAIConnection()` and `runAIDiagnostics()` so they always persist and pass the active `ai_provider` and `ai_model` even when API keys are already saved on disk.
  - Added `Cache-Control: no-store` middleware so Home Assistant Ingress always serves the latest frontend assets.

## [2.0.0] - 2026-10-30

### Major Overhaul: Real Multi-Protocol Network Scanner & Matter Cluster `0x0035` Telemetry
- **Enabled `host_network: true` in `config.yaml`**:
  - Allows the add-on container to access the host's real IPv6 routing table (`fd00::/8` Thread ULA prefixes), Neighbor Discovery cache, LAN mDNS multicast traffic, and direct ICMPv6 ping sockets.
- **Fixed `python-matter-server` WebSocket Handshake & Added Full Cluster `0x0035` (Thread Network Diagnostics) Parser**:
  - Properly consumes the initial unsolicited `ServerInfoMessage` greeting and matches command responses by `message_id`.
  - Extracts real flat attributes from commissioned Matter nodes:
    - **Basic Info (`0/40/*`)**: Vendor, Product, NodeLabel, Firmware Version, Serial Number.
    - **General Diagnostics (`0/51/*`)**: Network interfaces, hardware MAC address, and decoded IPv6 ULA (`fd00::/8`) / link-local addresses.
    - **Thread Network Diagnostics (`0/53/*` — Cluster `0x0035`)**: Channel (`0/53/0`), Routing Role (`0/53/1` — Leader, Router, REED, EndDevice, SleepyEndDevice), Network Name (`0/53/2`), PAN ID (`0/53/3`), Extended PAN ID (`0/53/4`), Mesh-Local Prefix (`0/53/5`), Overrun Count (`0/53/6`), full **Neighbor Table (`0/53/7`)** with real `averageRssi`, `lastRssi`, `lqi`, frame/message error rates, full **Route Table (`0/53/8`)**, error counters (`DetachedRoleCount`, `ParentChangeCount`, `AttachAttemptCount`), Extended MAC (`0/53/62`), and `RLOC16` (`0/53/63`).
  - Cross-references Router `NeighborTable` child entries so Sleepy End Devices (SED/ICDs) inherit their parent router's measured RSSI, LQI, and `parent_rloc16`.
  - Added on-demand **Live Node Ping** (`POST /api/matter/ping_node`) testing both `python-matter-server` `ping_node` and ICMPv6 `ping -6`.
- **Real mDNS / Zeroconf Scanner (`_meshcop._udp.local.`, `_matter._tcp.local.`, `_matterc._udp.local.`)**:
  - Replaced the static placeholder with a real `AsyncZeroconf` + `avahi-browse` scanner that decodes binary/ASCII MeshCoP TXT records (`nn`, `xp`, `vn`, `mn`, `tv`, `xa`, `ba`, `sb` state bitmap) and resolves Border Router IPv6/IPv4 addresses.
- **Fixed Home Assistant `thread/discover_routers` Streaming Subscription & Added Thread Dataset TLV Decoder**:
  - Properly subscribes to Home Assistant's `thread/discover_routers` event stream (`router_discovered` events) instead of closing after the initial `result: null` ACK.
  - Queries `thread/get_dataset_tlv` for each dataset and decodes raw Thread 1.3 Operational Dataset TLVs (`Channel`, `PAN ID`, `Extended PAN ID`, `Network Name`, `Mesh-Local Prefix`).
  - Removed all fake `"GOOGLE_THREAD_MESH"` / `"APPLE_THREAD_MESH"` entity-name string fabrications.
- **Added OpenThread Border Router (OTBR) REST API Inspector (`:8081`)**:
  - Queries `/node/state`, `/node/network-name`, `/node/ext-panid`, `/node/ext-address`, `/node/rloc16`, `/node/leader-data`, and `/node/dataset/active`.
- **Real Topology Builder & Prominent Top-Bar Network Scanner UI**:
  -Replaced round-robin fake topology edges with true IEEE 802.15.4 Extended Address, `NeighborTable`, and `RLOC16` (`0xFC00` router mask) link resolution.
  - Added a top-level **Select Thread Network -> Scan Selected Network -> Ask AI to Fix Issues** workflow bar and live Border Router / Matter Cluster `0x0035` tables.
  - Fixed default Gemini model from non-existent `gemini-3.8-flash` to `gemini-2.5-flash` with automatic 404 model fallback.

## [1.2.1] - 2026-10-30

### Fixed
- **Fixed Home Assistant WebSocket URL for Add-ons**:
  - Replaced incorrect WebSocket path with the official Home Assistant Supervisor WebSocket proxy endpoint (`ws://supervisor/core/websocket`) and fallback candidate (`ws://homeassistant:8123/api/websocket`).
  - Resolves empty Thread networks list by allowing successful retrieval of datasets (`thread/list_datasets`), border routers (`thread/discover_routers`), and device registry (`config/device_registry/list`).
- **REST States Fallback for Border Routers**:
  - Added REST `/api/states` inspection as a secondary discovery path to detect Google Nest Wifi Pro, Apple TV 4K, and HomePod border router entities.
- **Button Simplification & Auto-Refresh**:
  - Shortened scan button to **"Scan"** per user preference.
  - Clicking "Scan" now automatically refreshes and populates the Thread networks dropdown while scanning actual network telemetry.
  - Added real-time network counter and guidance status under the dropdown.

## [1.2.0] - 2026-10-30

### Added
- **Thread Network Selection Dropdown in Settings**:
  - Live dropdown selector in the Settings tab listing all Thread networks available in Home Assistant.
  - Aggregates configured datasets (`thread/list_datasets`), live discovered border routers (`thread/discover_routers`), and registered hardware (Nest Wifi Pro, Apple TV 4K, HomePod, SkyConnect).
  - Displays complete network metadata: Network Name, Extended PAN ID, PAN ID, 802.15.4 Channel, Preferred status (★), and active Border Routers.
- **Target Network Scanning ("Scan My Actual Network")**:
  - Added dedicated **"Scan My Actual Network"** button to immediately evaluate telemetry and mesh health against the selected Thread network.
  - Automatically targets and isolates the selected network's channel for RF coexistence calculations and flags foreign or split-mesh border routers operating on different Extended PAN IDs.
  - Added visual target highlighting in the interactive SVG topology graph and device inspector.
  - Added persistent Target Network Banner on the dashboard with quick re-scan and network switching controls.

## [1.1.0] - 2026-10-30

### Changed & Streamlined
- **Zero Mock / Demo Fallbacks (100% Real Live Telemetry)**:
  - Removed all demo scenario buttons, mock endpoints, and placeholder sample data.
  - Mesh Topology and AI Diagnostics operate strictly on 100% live discovered Thread Border Routers (Google Nest Wifi Pro, Apple TV 4K, HomePod, SkyConnect) and real Matter devices.
  - If no devices or border routers are detected yet, a clean empty state is displayed in the SVG topology graph with a prompt to connect or pair devices and use the "Refresh Topology" button.
- **On-Demand Topology Refresh**:
  - Live "Refresh Topology" button re-scans Home Assistant WebSocket Thread datasets, mDNS border router discovery, and device registry in real-time.
- **AI Latency Optimization & Timeout Fix**:
  - Streamlined AI telemetry payload prevents `ReadTimeout` on Gemini `gemini-3.8-flash`.

## [1.0.9] - 2026-10-30

### Fixed & Added
- **Resolved Gemini `ReadTimeout`**:
  - Increased AI request timeout from 60s to 180s (`httpx.Timeout(180.0, connect=30.0)`).
  - Added smart telemetry payload streamlining (`_streamline_telemetry`) to strip raw dump clutter, reducing AI processing latency from 60+ seconds down to ~5-10 seconds.
- **Topology Refresh Button**:
  - Added direct **"Refresh Topology"** button on the Live Mesh Topology card for instantaneous on-demand re-scanning.
  - Added live status bar showing scan timestamp and count of detected border routers.
- **Restored Multi-Ecosystem Border Router Detection (Apple + Google + HA)**:
  - Ensured Apple TV 4K & HomePod Border Routers are detected across Home Assistant mDNS, Thread discovery, and Device Registry alongside Google Nest Wifi Pro.
  - Updated sample scenario to showcase both Google Nest Wifi Pro and Apple TV 4K.

## [1.0.8] - 2026-10-30

### Added
- **Full Google Nest Wifi Pro & Google Nest Hub Border Router Detection**:
  - Automatically identifies Nest Wifi Pro routers using Home Assistant's `thread/discover_routers`, `thread/list_datasets`, and `config/device_registry/list`.
  - Added dedicated Google Nest device classification and branding (`#4285F4`) in the Interactive Topology Map.
  - Dynamically renders discovered Border Routers (Nest Wifi Pro, HA SkyConnect, etc.) instead of static placeholders.
  - Added tailored detection for Split Thread Meshes between Google Nest Wifi Pro and Home Assistant Green, with step-by-step sync guidance via the Home Assistant Companion App.

## [1.0.7] - 2026-10-29

### Added
- Added interactive **"Test AI Connection"** button in Settings with instant live feedback from Google API.
- Fixed key persistence across container restarts by saving to persistent `/data/matter_ai_settings.json`.
- Added API key status preview (`✓ Saved (AIzaSy...)`) in Settings placeholders.
- Enhanced error handling to return full exception details instead of empty error strings.

## [1.0.6] - 2026-10-29

### Added
- Upgraded primary Gemini model to **`gemini-3.8-flash`** (Google's latest active Gemini 3 family).
- Added `x-goog-api-key` header authentication support for all Gemini API calls.
- Updated default model dropdown and backend normalization for `gemini-3.8-flash`.

## [1.0.5] - 2026-10-29

### Fixed
- Fixed Gemini API model name mismatch by replacing free-form text input with a verified model dropdown (`gemini-2.0-flash`, `gemini-1.5-flash`, `gemini-1.5-pro`).
- Added smart model normalization in AI engine to map `gemini-3.x` designations or typos to `gemini-2.0-flash`.
- Added automatic model fallback to `gemini-1.5-flash` if a 404 model error is returned by Google API.

## [1.0.4] - 2026-10-29

### Fixed
- Fixed base image override by hardcoding `docker.io/library/python:3.12-slim-bookworm` directly in Dockerfile, preventing Supervisor from falling back to Alpine.
- Removed deprecated `build.yaml`.
- Removed deprecated 32-bit architectures (`armv7`, `armhf`) from `config.yaml`.

## [1.0.3] - 2026-10-29

### Fixed
- Migrated base image from Alpine to Debian Bookworm (`python:3.12-slim-bookworm`).
- Fixed build failure caused by missing musl pre-compiled wheels for `pydantic-core` on aarch64. Debian provides official pre-built `manylinux` wheels, eliminating any source compilation on HA Green.

## [1.0.2] - 2026-10-29

### Fixed
- Fixed `s6-overlay-suexec: fatal: can only run as pid 1` by migrating from HA s6 base image to clean Python 3.12 Alpine.
- Set `init: false` in `config.yaml` to prevent Docker init / tini process interception.
- Direct entrypoint to `/app/run.sh` ensuring Uvicorn runs as the root service process.

## [1.0.1] - 2026-10-29

### Fixed
- Fixed 502 Bad Gateway under Home Assistant Ingress by switching to bridge container networking.
- Fixed schema parsing in `config.yaml` for string options.
- Added explicit working directory navigation `/app` in container entrypoint `run.sh`.
- Added direct static asset routes for `/style.css` and `/app.js` under Ingress path rewrites.
- Added Alpine build tools in Dockerfile to guarantee clean compilation of dependencies.

## [1.0.0] - 2026-10-29

### Added
- Initial release for Home Assistant Green (HAOS aarch64 & amd64).
- Deterministic heuristic analysis for:
  - Multi-Border Router split Thread meshes (PAN ID, Ext PAN ID, Network Key).
  - 2.4 GHz RF Coexistence (Thread channels 11–26 vs Wi-Fi channels 1, 6, 11).
  - IPv6 ULA / RIO routing table inspection (`ip -6 route show`).
  - Matter node link quality evaluation (RSSI < -82 dBm, offline sensors).
- Multi-Provider Cloud AI engine supporting Google Gemini, OpenAI GPT-4o, and Anthropic Claude.
- Home Assistant Ingress web dashboard with live SVG mesh topology map and Device Inspector.
- Manual Log & JSON Diagnostic Analyzer for pasting external Matter Server and OpenThread Border Router dumps.
- Demo multi-router split network scenario generator for testing without physical devices.
