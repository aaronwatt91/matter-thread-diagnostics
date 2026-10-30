# Changelog

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
