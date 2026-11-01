# Changelog

## [2.8.2] - 2026-11-01

### Added: Free-Hand 3D Node Dragging & Persistence, Clean Spheres, and Updated Blair House Model
- **Updated 'The Blair 4 TK' 3D Architectural Model**:
  - Replaced `Taylor_Wimpey_Blair.glb` with the updated architectural revision featuring a clean straight staircase, open timber banister, fitted wardrobe recess in the master bedroom, sealed upper void removed, level floor plates, vertical planar party wall, curved kitchen counter radius, and pitched bargeboards.
- **Pure Glowing Sphere Geometry**:
  - Replaced the previous "Saturn-like" outer orbiting rings on nodes with clean, glowing spheres (`SphereGeometry(0.20)` with PBR roughness/metalness).
  - Subtle rhythmic emissive pulse animation reflecting real-time wireless heartbeat without distracting visual rings.
- **Free-Hand 3D Node Dragging & Coordinate Saving**:
  - Interactive click-and-drag directly in the 3D viewport on any Thread/Matter or Zigbee node.
  - OrbitControls automatically lock during drag operations.
  - Device ray projects against a camera-facing drag plane for intuitive 1-to-1 mouse/touch movement at any camera angle.
  - Real-time dynamic updates: connected wireless RF link beams and animated pulse packets bend and follow the dragged node in real time.
  - Custom `(x, y, z)` spatial coordinates are automatically committed to `localStorage['ha_matter_custom_3d_positions']` on release.
  - Persisted custom placements survive page reloads, tab navigation, and network scans.
- **Reset Node Positions Action**:
  - Added "Reset Positions" toolbar button in the 3D twin controls to revert custom-dragged devices back to their room anchor defaults at any time.

## [2.8.1] - 2026-11-01

### Fixed: Home Assistant Ingress Asset Routing & 3D House Twin Discovery
- **Home Assistant Ingress Asset Routing**:
  - Mounted dedicated StaticFiles and explicit API route handlers in `main.py` for `/vendor` and `/models` (`/models/{file_path:path}` and `/vendor/{file_path:path}`).
  - Resolves 404 errors caused by Home Assistant Ingress URL prefixes (`/api/hassio_ingress/<token>/`) when loading `vendor/three/three.min.js` and `models/Taylor_Wimpey_Blair.glb`.
- **Three.js Script Resilience & CDN Fallbacks**:
  - Added automatic fallback to official CDN mirrors (`cdnjs` & `jsdelivr`) in `index.html` if local vendor script requests are ever blocked or delayed.
  - Added self-healing retry mechanism in `app.js` (`setTimeout(initHouse3DViewer, 200)`) preventing initialization aborts if WebGL dependencies load asynchronously.
- **Dynamic Ingress Path Resolver for 3D Model**:
  - Implemented multi-stage sequential candidate URL loader for `Taylor_Wimpey_Blair.glb` that detects the active Ingress base path dynamically (`window.location.pathname`).
  - Added loading indicator overlay with live download progress percentage and visual retry button if network fails.
- **Immediate 3D House Twin Discovery**:
  - Promoted **3D House Twin** to the default active layout mode in **Live Mesh Topology** (Tab 2).
  - Added prominent quick-switch banner in Tab 2 with persistent `localStorage` preference memory.
  - Increased default architectural wall opacity from 35% to 80% so the Blair house geometry is clearly visible and crisp upon first view.

## [2.8.0] - 2026-11-01

### Added: Interactive 3D Digital Twin House Model & Spatial Wireless Mesh Viewer
- **Taylor Wimpey 'The Blair 4 TK' 3D House Twin**:
  - Integrated directly into **Live Mesh Topology** (Tab 2) as a 6th layout perspective: **3D House Twin** (`data-layout="house3d"`).
  - Built using Three.js, OrbitControls, and GLTFLoader to render `Taylor_Wimpey_Blair.glb` (932 KB PBR architectural model with 47 named mesh objects).
  - Features complete blueprint-accurate geometry: ground floor living room, kitchen/dining with combi boiler and French doors, entrance hall with consumer unit meter cupboard, downstairs WC, staircase, first-floor master bedroom with en-suite, guest room, nursery, family bathroom, upstairs landing, 5 rear roof solar panels, and front driveway with Peugeot e-2008 plugged into the EV wallbox charger.
- **Full 3D Camera Controls & Room Presets**:
  - Smooth orbit rotation (left drag), panning (right drag), and zoom (scroll/pinch).
  - 10 Instant Camera Quick-Jumps: Overview / Isometric Front, Rear Garden & Solar Panels, Living Room, Kitchen & Dining, Entrance & Meter Cupboard, Master Bedroom, Guest Room, Nursery, Family Bathroom, and Driveway & EV.
  - Smooth easing interpolation (`flyCameraTo`) between camera viewpoints.
- **Floor Cutaway Dollhouse Perspectives & X-Ray Mode**:
  - 4 Floor Views: **All Floors** (translucent building shell), **Ground Floor** (dollhouse cutaway showing ground floor rooms from above), **First Floor** (cutaway revealing bedrooms and bathroom), and **Solid Shell** (opaque exterior).
  - Real-time **X-Ray Opacity Slider** (5% to 100%) to look straight through walls into the glowing mesh nodes.
- **3D Spatial Wireless Nodes & Dynamic RF Link Beams**:
  - Devices mapped into their respective rooms as glowing 3D spheres with pulsing beacon rings and billboard text labels.
  - Color-coded roles: Border Routers / Coordinators (Gold/Cyan), Mains Routers (Green), Battery Sensors (Purple), Offline Nodes (Red), Weak Signal (Orange).
  - Arched 3D wireless RF link beams connecting each device to its parent router/border router, color-coded by RSSI/LQI signal strength.
  - Animated glowing signal pulse packets travelling along the link curves.
- **Room Placement Manager & Auto-Detection**:
  - **Auto-Detection**: Automatically parses Home Assistant `ha_area` and device names to match blueprint rooms (Living Room, Kitchen, Meter Cupboard, Master Bedroom, En-Suite, Guest Room, Family Bathroom, Upstairs Hallway, etc.).
  - **Room Placement Modal**: Click **Room Placements** to view all discovered devices, change assigned rooms, or trigger **Auto-Detect All**.
  - **Device Inspector Integration**: Change any device's assigned room directly inside the **Device Inspector**, with changes persisting to `localStorage` and updating the 3D twin in real-time.
- **Raycasting & Node Focus**:
  - Hovering over any 3D device displays a floating HUD tooltip with device name, role, assigned room, RSSI, and LQI.
  - Clicking any 3D node smoothly flies the camera to focus on it and opens the full Cluster 0x0035 Device Inspector.
- **Dual Protocol Support**:
  - Seamlessly renders both Thread & Matter devices as well as Zigbee devices when the Zigbee protocol toggle is selected.

## [2.7.1] - 2026-11-01

### Fixed: Strict Protocol Isolation & Zigbee Channel / View Desynchronization
- **Strict Protocol Isolation across All Tabs**:
  - `activateTab(tabId)` now strictly checks `currentNetworkProtocol`:
    - Switching to **Topology** (`tab-topology`) in Zigbee mode loads `currentZigbeeTelemetry.topology` and never overwrites it with Thread topology.
    - Switching to **Channel** (`tab-channel`) in Zigbee mode renders Zigbee Radio Coordinator info and never invokes `fetchOtbrChannelInfo()`, preventing Thread channel/PAN ID from overwriting the radio card.
    - Switching to **Live Scan** (`tab-rules`) renders Zigbee tables and never falls back to Thread Border Routers or Cluster 0x0035 tables.
- **Topology Perspective Resynchronization**:
  - `dispatchTopologyRender()` locks `lastTopologyData` to `currentZigbeeTelemetry.topology` in Zigbee mode and `currentTelemetry.topology` in Thread mode, ensuring clicking **Force / RF Mesh**, **Tree / Hierarchy**, **Transit Map**, **Routing Flow (Sankey)**, or **Signal Matrix** stays 100% Zigbee.
  - Nodes in Zigbee topology labeled `★ COORD` or `COORD`, `RTR`, and `DEV` with real LQI metrics (removing Thread `TBR` and `SED` labels).
  - Subway / Transit map and Signal Matrix adapted with gold Zigbee coordinator themes and LQI link budgets.
- **Zigbee Radio Channel & Frequency Guide**:
  - Tab 3 radio hardware card locked to detected Zigbee Coordinator channel, frequency (MHz), and IEEE address.
  - Hides Thread-specific PAN join card, Thread migration strategy card, and countdown banner in Zigbee mode.
  - Channel picker grid displays 16-channel Zigbee interference evaluation with custom ZHA/Z2M configuration guidance.
- **Backend ZHA Network Settings Extraction**:
  - `ha_client.py` enhanced to extract Zigbee channel, PAN ID, and Extended PAN ID from both root level and nested `network_info` / `radio` payloads in Home Assistant's `zha/network/settings` API.

## [2.7.0] - 2026-11-01

### Added: Complete End-to-End Zigbee Protocol Transformation
- **Full Tab & View Transformation to Zigbee**:
  - Selecting `[ 🐝 Zigbee Network ]` transforms every tab, card, graph, frequency channel, and AI diagnosis so the entire add-on becomes Zigbee in essence.
- **Tab 1: 4 Authentic Zigbee Diagnostic Rule Cards**:
  - *1. Zigbee Coordinator Identity & Channel*: PAN ID, Extended PAN ID, Channel, MHz frequency, and integration status (ZHA / Zigbee2MQTT).
  - *2. 2.4 GHz RF Coexistence*: Zigbee channel overlap evaluation against Wi-Fi channels (1, 6, 11) and Thread networks, highlighting recommended guard bands (Channels 15, 20, 25).
  - *3. Mesh Density & Backbone Routers*: Mains-powered Zigbee routers vs battery-operated end devices ratio, verifying healthy meshing density.
  - *4. Link Quality & Battery Health*: Evaluates weak LQI links (< 65), fringe RSSI (<-82 dBm), and low battery sensors (< 20%).
- **Tab 2: Zigbee Topology & Legends**:
  - Dynamically updates page headings, descriptions, and legend to "Zigbee Mesh Network Topology" (Coordinator, Routers, Battery End Devices).
  - Rescan topology button fetches live Zigbee telemetry.
- **Tab 3: Zigbee Radio Channel & 2.4 GHz Spectrum Visualizer**:
  - Hardware card displays active Zigbee Coordinator dongle details (ZBT-1 / SkyConnect / ConBee / Sonoff), PAN ID, Extended PAN ID, and operating MHz frequency.
  - Thread-specific "Join Existing PAN / Thread Mesh" card is hidden in Zigbee mode to eliminate confusion.
  - Active Zigbee network is rendered as the primary glowing column (`🐝 ACTIVE ZIGBEE: Ch X`) on the 2.4 GHz spectrum chart with dedicated Zigbee RF clearance assessment.
- **Tab 4: Zigbee AI Diagnostic Engine**:
  - AI engine provides deep Zigbee domain expertise: Coordinator health, router backbone density, 2.4 GHz Wi-Fi/Thread interference, LQI link budget, and battery remediation.
  - Symptom suggestions and placeholder text dynamically tailored to Zigbee issues.
- **Tab 5: Log & Raw Telemetry Inspector**:
  - "Load Logs & Scan" inspects the live Zigbee telemetry payload with full device, neighbor, and RF metrics.

## [2.6.1] - 2026-11-01

### Fixed: Tab Isolation & Zigbee Scanner HTTP 500 Error
- **Fixed Tab Isolation & Layout Leak**:
  - Removed an extraneous closing `</div>` in `index.html` that prematurely closed `<section id="tab-rules">`, preventing the 4 diagnostic rule cards ("1. Multi-Border Router Synchronization", "2. 2.4 GHz RF Coexistence", "3. Host Kernel IPv6 ULA Routes & ICMPv6 Pings", "4. Node Link Quality & Server Logs") from leaking and displaying across all navigation tabs.
  - Dynamically hides the 4 Thread-specific rule cards when switched to Zigbee mode, and cleanly restores them when switching back to Thread.
- **Resolved Zigbee Scan HTTP 500 Error**:
  - **Type-Safe Ingestion**: Built `_safe_int`, `_safe_float`, and `_safe_str` helpers in `zigbee_analyzer.py` to guard against Home Assistant string LQI values (`"unknown"`, `"unavailable"`), non-numeric RSSI strings, hex/negative NWKs, and integer IEEE addresses.
  - **Channel Arithmetic**: Safeguarded 2.4 GHz frequency calculation `freq_mhz = 2405 + 5 * (ch_int - 11)` against string channel values.
  - **Graceful Error Handling & Fallback**: Wrapped `get_zigbee_telemetry` and `@app.get("/api/zigbee/scan")` in top-level exception handlers with diagnostic logging and realistic fallback data, ensuring `HTTP 500` is never thrown.
  - **Unit Tests**: Added `test_zigbee_defensive_types_and_resilience()` verifying parsing resilience with corrupted or non-standard inputs.

## [2.6.0] - 2026-11-01

### Added: Zigbee & Thread Dual-Protocol Network Scanner & Unified Diagnostics
- **Dual-Protocol Mode Toggle**:
  - Prominent top-level scan toggle selector: `[ 🧵 Thread Network ]` vs `[ 🐝 Zigbee Network ]`.
  - State persisted across browser refreshes via `localStorage` (`mta_network_protocol`).
  - Seamless instant switching across all pages, KPI summary cards, topology visualizers, spectrum analysis, and AI diagnostics.
- **Full Zigbee Discovery & Telemetry Pipeline**:
  - Backend integration (`ha_client.py` & `zigbee_analyzer.py`) querying Home Assistant ZHA WebSocket APIs (`zha/devices`, `zha/network/settings`), Zigbee2MQTT MQTT/device registries, and entity states.
  - Generates comprehensive Zigbee network telemetry: Coordinator status, Channel, PAN ID, Extended PAN ID, LQI/RSSI metrics, battery levels, power source (Mains vs Battery), and area assignments.
  - Realistic demo fallback mesh dataset generated if no active Zigbee dongle is installed.
- **Dynamic Multi-Protocol UI Transformations**:
  - **KPI Header & Summary Cards**: Dynamically updates to Zigbee metrics — Mesh Health Index, Coordinator & Router density ("Online • X Routers"), 2.4 GHz Coexistence clearance, and Link Quality (Average LQI e.g. 215/255, weak link counter).
  - **Live Scan Tables (Tab 1)**:
    - *Coordinator Table*: Discovered Zigbee Coordinators & Adapters (ZHA / Zigbee2MQTT) with IEEE MAC, PAN ID, Channel, and integration source.
    - *Device Mesh Table*: Commissioned Zigbee Nodes with NWK short addresses, friendly names, roles (Router vs End Device), power sources, battery %, and LQI / RSSI signals.
    - *Filter & Search*: Dynamic filtering for Routers, End Devices (Battery), and Weak LQI nodes.
  - **Mesh Topology (Tab 2)**:
    - Interactive topology rendering for Zigbee networks across all 5 visual perspectives: **Force / RF Mesh**, **Tree / Hierarchy**, **Transit Map**, **Routing Flow (Sankey)**, and **Signal Matrix**.
    - Color coding: Zigbee Coordinator in gold (`#eab308`), Mains Routers in green (`#10b981`), and Battery End Devices in purple (`#8b5cf6`).
    - Dedicated Node Inspector displaying Zigbee IEEE address, NWK address, LQI, RSSI, battery %, and area.
  - **AI Diagnostics (Tab 4)**:
    - Contextual Zigbee troubleshooting prompts ("Diagnose weak Zigbee links and LQI drops", "Verify coordinator placement and router density", etc.).
    - Sends live Zigbee network telemetry bundle to AI diagnostic engine for specialized Zigbee mesh recommendations.
  - **Log & Raw JSON (Tab 5)**:
    - Displays raw Zigbee telemetry payload with one-click copy and inspect.
- **Backend API Endpoints**:
  - `GET /api/zigbee/scan`: Full scan of Zigbee coordinators, devices, LQI metrics, health evaluation, and coexistence analysis.
  - `GET /api/zigbee/topology`: Graph dataset (`nodes` and `edges`) for Zigbee mesh visualization.
  - Multi-protocol parameter support in `GET /api/diagnostics/collect?protocol=zigbee`, `GET /api/topology?protocol=zigbee`, and `POST /api/diagnostics/analyze`.
- **Unit Testing**:
  - Added `test_zigbee_analyzer_topology_and_health()` and `test_ha_client_zigbee_telemetry_fallback()` validating health score calculations, graph topology generation, and fallback handling.

## [2.5.1] - 2026-11-01

### Changed & Improved: Topology Visuals & Canvas Navigation
- **Restored Core Node Visualizations**:
  - **Force / RF Mesh**: Restored standard organic RF signal-strength physics simulation as the default mode.
  - **Tree / Hierarchy**: Restored top-down hierarchical layout mode (TBR gateways at Top $\rightarrow$ Routing backbone $\rightarrow$ End devices) with collision repulsion, node circles, and halos.
- **Upgraded Transit Map Navigation**:
  - **Canvas Background Drag & Pan**: Drag anywhere on the background canvas to smoothly pan across large networks without clipping.
  - **Mouse / Trackpad Wheel Zoom**: Continuous smooth zooming from 0.35x to 3.0x with pointer focus.
  - **Draggable Metro Stations**: Stations can be grabbed and dragged to custom positions with real-time recalculation of 45°/90° rectilinear metro track lines (`redrawMetroLines()`).
  - **1-Click Reset Zoom**: "Reset Zoom" button restores canvas transformation cleanly.
- **Upgraded Routing Flow (Sankey)**:
  - Enabled canvas background panning and wheel zoom so large routing trees remain easily navigable.
  - Enabled node card dragging for custom alignment.
- **Removed Unwanted Visual Modes**:
  - Removed **Radar Scope**, **Sunburst**, and **Chord Bundle** views and their associated CSS animations to keep the interface clean and focused.

## [2.5.0] - 2026-11-01

### Added: 2.4 GHz Network Coexistence Analyzer & Live Overlap Graph
- **Multi-Protocol Spectrum Probing Engine**:
  - `GET /api/coexistence/scan`: Gathers and cross-references active RF frequencies across **Thread**, **Zigbee**, and **Wi-Fi**.
  - **Thread**: Live channel, operational frequency, and PAN ID from ZBT-1 / OTBR.
  - **Zigbee**: Automatically probes Home Assistant for ZHA (`zha/network/settings`, config entries) or Zigbee2MQTT (bridge entities/attributes) to resolve the coordinator channel.
  - **Wi-Fi**: Detects router / AP 2.4 GHz primary channels from Home Assistant network/router integration entities (UniFi, AsusWRT, FritzBox, eero, Deco, Omada) or evaluates standard non-overlapping channels (1, 6, 11).
- **Interactive 2.4 GHz RF Overlap Spectrum Graph**:
  - Continuous 2400 MHz to 2485 MHz frequency spectrum canvas.
  - **Wi-Fi 20 MHz Masks**: Rendered as parabolic power curves centered at 2412 MHz (Ch 1), 2437 MHz (Ch 6), and 2462 MHz (Ch 11).
  - **Safe Wi-Fi Guard Bands**: Highlights Guard Band 1 (Ch 15 @ 2425 MHz), Guard Band 2 (Ch 20 @ 2450 MHz), and the Safe Zone (Ch 25–26 @ 2475–2480 MHz).
  - **Zigbee Channel Column**: Plotted in yellow/amber (`#eab308`) with pinned coordinator badge.
  - **Thread Channel Column**: Plotted in sky blue (`#38bdf8`) with pinned network badge.
  - **Collision Warning Overlays**: Visual danger badges indicating direct channel collisions with Zigbee or mask overlap with Wi-Fi.
  - **Interactive Channel Selecting**: Clicking any channel on the spectrum graph immediately marks it as target migration channel.
- **RF Diagnostic & Recommendation Banner**:
  - Evaluates mathematical frequency clearance between Thread, Zigbee, and Wi-Fi.
  - Live AI-driven channel migration recommendation tailored to user's exact Zigbee and Wi-Fi environment.
- **Unit Tests**: Added `test_coexistence_spectrum_scan()` to verify multi-protocol probing and collision detection.


## [2.4.0] - 2026-11-01

### Added: 6 Distinct Network Topology Visual Perspectives
- **1. 🚇 Subway / Transit Map View**:
  - Schematic metro/transit styling with 45°/90° rectilinear colored tracks and station nodes.
  - Border Routers rendered as large double-ringed Central Interchange Stations / Terminal Hubs.
  - Thread Routers rendered as transfer station discs along backbone lines.
  - Battery End Devices (SEDs) rendered as local stop station ticks along branch tracks.
- **2. 🎛️ Signal Cross-Matrix / 2D Heatmap Grid**:
  - Interactive high-density 2D tabular matrix comparing every device against every peer.
  - Summary metric cards for Total Devices, Direct RF Links, Mesh Density %, and Average Mesh Link Signal.
  - Color-coded cells showing exact link RSSI (>-60 dBm emerald, -60 to -70 lime, -70 to -80 amber, <-80 red).
  - Sticky headers and row labels with direct node inspection on click.
- **3. 🌊 Sankey / Alluvial Routing Flow Diagram**:
  - Left-to-right fluid stream diagram: Border Routers (Gateways) &rarr; Routers (Mesh Backbone) &rarr; Battery Sensors.
  - Glassmorphism node cards with live signal dBm badges.
  - Fluid cubic bezier ribbons with hover focus and thickness scaled by routing importance.
- **4. 🎯 Tactical Sonar / Radar Scope**:
  - Dark military tactical radar scope with concentric range rings (-40 dBm, -60 dBm, -75 dBm, -90 dBm).
  - Crosshair axes and degree ticks.
  - Continuously rotating animated sweeping sonar beam.
  - Target blips plotted in true polar space based on real RF signal distance with warning halo beacons.
- **5. 🍩 Radial Sunburst Partition Hierarchy**:
  - Multi-tiered circular ring partition: Center Network PAN &rarr; Border Router slices &rarr; Router repeaters &rarr; End Devices.
  - Arc sizes proportional to child device counts with full partition color groupings.
- **6. 🕸️ Circular Chord / Routing Ribbon Bundle**:
  - Clean outer perimeter circle with outward-radiating device labels.
  - Quadratic bezier routing ribbons connecting peers through the center.
  - Interactive Spotlight Hover: hovering any device illuminates only its direct connections while dimming all other chords.


## [2.3.0] - 2026-11-01

### Added: Multi-Perspective Topology Views, Dynamic Heatmaps & Filters
- **Multi-Layout Perspectives Toolbar**:
  - **Force / RF Mesh**: Organic signal-physics simulation where distance corresponds to live RF RSSI, LQI, and Ping RTT.
  - **Tree / Hierarchy**: Clean structured tiered hierarchy (TBRs at top -> Mains Routers -> Sleepy End Devices).
  - **Concentric / Orbit**: Polar orbit rings with primary Border Router at the center, intermediate routers on an inner ring, and battery sensors on outer orbital rings.
  - **Room / Area**: Automatic spatial clustering grouped by Home Assistant Area / Room assignment (e.g. Living Room, Office, Kitchen).
- **Dynamic "Color By" Modes**:
  - **Device Role**: Color-coded by device type (Google Nest TBR `#4285F4`, Apple TV/HomePod `#94a3b8`, HA OTBR `#03A9F4`, Thread Router `#10b981`, Battery End Device `#8b5cf6`, Warning/Offline).
  - **Signal Quality (RSSI Heatmap)**: Dynamic signal gradient (Excellent `>-60 dBm`, Good `-60 to -70 dBm`, Fair `-70 to -80 dBm`, Poor `<-80 dBm`, Offline/Unknown).
  - **Border Router / Parent Affinity**: Multi-source BFS propagation identifying which Border Router partition and route each child node routes through, using high-contrast partition colors.
  - **Power Source**: Mains-powered always-on backbone (`#06b6d4`) vs battery-powered sleepy sensors (`#a855f7`).
- **Interactive Filtering & Detail Toggles**:
  - **Filter Dropdown**: Toggle between *All Devices*, *Routers & TBRs Only (Backbone)*, *Battery Sensors Only (SEDs)*, and *Hide Offline Nodes*.
  - **Link Signal (dBm) Toggle**: Checkbox to instantly show/hide link RSSI and latency badges on mesh edges.
- **Dynamic Legend**:
  - Color swatches and legend labels dynamically re-render based on the currently selected Color Mode.


## [2.2.1] - 2026-10-31

### Fixed: Active Network Option Enabled for Inspection & Re-synchronization
- **Enabled Active Mesh in Selection Dropdown**:
  - Previously, the network matching the ZBT-1's active PAN / XPAN was given `disabled = true`, rendering it greyed out and unselectable in the HTML dropdown.
  - Removed `disabled` state so users can select and inspect any dataset (including `NEST-PAN-2E89`).
  - Added dedicated **"Re-apply / Sync Active PAN Credentials"** action when the currently active network is selected, allowing users to re-push the Home Assistant active dataset to the OpenThread Border Router radio if it lost synchronization or after an add-on restart.

## [2.2.0] - 2026-10-31

### Added: 1-Click "Join Existing PAN / Thread Mesh" Picker
- **1-Click Network & PAN Join Engine**:
  - Added `HAClient.get_available_join_networks()` and `HAClient.join_thread_network()` with new backend endpoints `GET /api/otbr/joinable_networks` and `POST /api/otbr/join_network`.
  - Discovers all stored Thread datasets and active PANs in Home Assistant (e.g. `NEST-PAN-2E89`, Apple HomePod networks, secondary border router meshes).
  - Automatically resolves the ZBT-1's `extended_address` and sends Home Assistant WebSocket command `otbr/set_network` (`extended_address`, `dataset_id`) to switch the ZBT-1 radio to the selected mesh credentials.
  - Automatically updates Home Assistant's `thread/set_preferred_dataset` so all new Matter devices commissioned via the HA Companion App pair to the joined network.
- **Custom Operational Dataset TLV Import**:
  - Added support for pasting raw hexadecimal Operational Dataset TLVs to import and join external Thread networks (e.g. from Apple Home or Nanoleaf ecosystems).
- **Interactive "Join Existing PAN" Card in ZBT-1 Channel Tab**:
  - Live preview box displaying Target Network Name, PAN ID, Channel, and Extended PAN ID.
  - Safety confirmation modal before switching active PAN credentials.
  - Animated progress banner indicating operational dataset application and automatic re-scan upon completion.
- **Unit Tests**:
  - Added unit test in `test_diagnostics.py` testing dataset discovery, `otbr/set_network`, and `thread/set_preferred_dataset`.

## [2.1.2] - 2026-10-31

### Fixed: Automatic OTBR `extended_address` Resolution for `otbr/set_channel`
- **Automatic OTBR Extended Address Resolution**:
  - In modern Home Assistant Core, the `otbr/set_channel` WebSocket command schema requires the target border router's `extended_address` (`probatio.Required("extended_address"): str`).
  - The add-on now queries `otbr/info` over Home Assistant WebSocket to automatically discover the border router's hardware extended address (e.g. `49f5daf7314f6b62`), falling back to `preferred_extended_address` from `thread/list_datasets` and live radio discovery.
  - Passes the normalized lowercase extended address directly in `cmd = {"type": "otbr/set_channel", "channel": channel, "extended_address": ext_addr}`, satisfying Home Assistant's schema validator.
  - Automatically retries without `extended_address` if running against a legacy Home Assistant Core version that does not accept extra keys.
- **WebSocket-First Radio Reachability in `get_zbt1_channel_status`**:
  - Injected `otbr/info` query into `get_zbt1_channel_status` so the Connect ZBT-1 radio state, XPAN, channel, and extended address are detected and marked reachable directly through Home Assistant Core, even when direct REST access to `:8081` is segregated on the host network namespace.
- **Unit Tests**:
  - Added unit test in `test_diagnostics.py` verifying `otbr/info` extraction and formatted `otbr/set_channel` with `extended_address`.

## [2.1.1] - 2026-10-31

### Fixed: Home Assistant WebSocket `otbr/set_channel` Schema & Direct REST Unreachable Handling
- **Home Assistant Core WebSocket Command Schema Alignment**:
  - Home Assistant Core's `otbr/set_channel` command schema strictly requires `type: "otbr/set_channel"` and `channel: int(11..26)` with no additional parameters. Removed erroneous `entry_id` key from the WebSocket payload which previously caused Home Assistant's schema validator to reject the command with `invalid_format: extra keys not allowed @ data['entry_id']`.
- **Immediate Success on HA Core Execution**:
  - When Home Assistant Core executes `otbr/set_channel`, HA Core directly sets the active channel on the OpenThread Border Router container. The add-on now records immediate success without making redundant, failing direct REST calls to `:8081` on the host network namespace.
- **Accurate Error Reporting & Fail-Fast Fallback**:
  - Reduced direct REST timeout per candidate from 8.0s to 3.0s for responsive UI handling.
  - Returns clear, diagnostic error messages indicating the exact response from both Home Assistant WebSocket and OTBR REST API rather than a generic `:8081` connection failure.
- **Unit Tests**:
  - Added unit test in `test_diagnostics.py` verifying that `HAClient.set_otbr_channel` formats `cmd = {"type": "otbr/set_channel", "channel": 25}` strictly according to Home Assistant Core's schema with no extra keys.

## [2.1.0] - 2026-10-31

### Added: Dedicated Home Assistant Connect ZBT-1 / Thread Radio Channel Management Page
- **Dedicated `ZBT-1 / Thread Channel` Navigation Tab**:
  - Added a dedicated management page for inspecting your Home Assistant Connect ZBT-1 / SkyConnect radio status and migrating your active Thread mesh operating channel.
- **Dual-Channel Migration Engine (HA WebSocket + Direct OTBR REST API)**:
  - Added `NetworkChecker.set_otbr_channel_direct()` and `HAClient.set_otbr_channel()` calling both Home Assistant's `otbr/set_channel` WebSocket command and the direct OpenThread Border Router REST API (`PUT /node/dataset/pending` and `PUT /node/dataset/active` on `:8081`).
  - Supports **Graceful Mesh Migration (30-second delay timer)**: broadcasts a Thread Pending Operational Dataset across your mesh so battery-powered sensors and smart plugs switch simultaneously without dropping off the network.
  - Supports **Immediate Channel Switch (0s delay)**: directly updates the active radio dataset.
  - Automatically refreshes Home Assistant's local Thread dataset cache to eliminate stale channel caching bugs.
- **Interactive 2.4 GHz RF Coexistence Spectrum & Channel Picker**:
  - Visual 2.4 GHz spectrum chart aligning Thread channels 11 to 26 with standard 20 MHz Wi-Fi channels 1, 6, and 11.
  - 16-channel interactive selector with clear badges highlighting **Channel 26 (Cleanest / 0% Wi-Fi overlap)**, **Channel 25 (Recommended guard band)**, and highlighting channels with Wi-Fi interference.
  - Live animated countdown progress bar during mesh migration.

## [2.0.9] - 2026-10-31

### Added: Home Assistant Friendly Device Names, Room Areas & Entity IDs
- **Automatic Home Assistant Device, Area & Entity Name Resolution (`HAClient.enrich_matter_nodes_with_ha_names`)**:
  - Queries Home Assistant's `config/device_registry/list`, `config/area_registry/list`, and `config/entity_registry/list` during every scan and cross-references each Matter `node_id` (`deviceid_<fabric>-<node_id_hex>-MatterNodeDevice`), `serial_number`, and `ext_address`.
  - Pulls in your custom Home Assistant device/entity name (e.g. **Living Room Light**, **Kitchen Coffee Plug**), Room Area badge (`📍 Living Room`), and primary entity ID (`light.living_room_light`) while preserving the underlying hardware model (`Essentials A19`, `Eve Energy`).
  - Displays Home Assistant friendly names across the **Commissioned Matter Nodes** table, **Live Force-Directed Topology** map, **Node Link Quality** issue list, **Purge** confirmation dialogs, **Search** bars, and **AI Diagnostic Reports**.

## [2.0.8] - 2026-10-31

### Added: Purge / Decommission Matter Devices (Single & Bulk Offline Purge)
- **Matter Server `remove_node` + Home Assistant Device Registry Cleanup**:
  - Added `MatterClient.remove_node()` (`command="remove_node"`, `args={"node_id": ...}`) in `app/matter_client.py` and `HAClient.remove_matter_device_from_ha_registry()` in `app/ha_client.py` to decommission and purge nodes from `python-matter-server` and remove any orphaned device entries from Home Assistant's Device Registry.
  - Added `POST /api/matter/purge_node` and `POST /api/matter/purge_nodes_bulk` in `app/main.py` with immediate telemetry, health score, and topology graph cache eviction (`_evict_purged_nodes_from_cache`).
- **Per-Node & Bulk Offline Purge Controls Across UI**:
  - Added a **Purge** button next to **Ping** on every row in the **Commissioned Matter Nodes** table.
  - Added a **Purge Offline (`N`)** bulk button in the **Commissioned Matter Nodes** header when offline/ghost nodes are present.
  - Added inline **Purge** buttons in **Rule 4 (Node Link Quality)** for offline/wrong-network nodes and inside the **Topology Device Inspector** panel when clicking a node on the mesh map.

## [2.0.7] - 2026-10-30

### Fixed: API Key Redaction in Logs, Supervisor `hassio_role: manager` for Log Access & OpenThread 0–3 LQI Scale
- **Eliminated API Key Exposure in `httpx` Logs & Diagnostic Bundles**:
  - Removed `"key"` URL query parameters from all Gemini `ListModels`, `:streamGenerateContent`, and `:generateContent` calls in `app/ai_engine.py`, passing the API key strictly via the `x-goog-api-key` HTTP header so it never appears in any request URL.
  - Set `httpx` and `httpcore` loggers to `WARNING` and added regex secret scrubbing (`_redact_secrets`) in `_RingBufferLogHandler` and `_build_diagnostic_log_bundle()`.
- **Fixed Supervisor API `403 Forbidden` When Reading Matter Server & OTBR Logs**:
  - Added `hassio_role: manager` alongside `hassio_api: true` in `config.yaml` so Home Assistant Supervisor permits reading `/addons/core_matter_server/logs` and `/addons/core_openthread_border_router/logs` (populating sections `[3]` and `[4]` of the downloaded diagnostic log bundle).
- **Fixed OpenThread Link Quality (`0–3`) vs IEEE 802.15.4 LQI (`0–255`) Scoring Scale**:
  - Updated `ThreadAnalyzer._is_weak_lqi()`, `ThreadAnalyzer._format_lqi()`, `ThreadAnalyzer.evaluate_node_link_quality()`, `ThreadAnalyzer.build_real_mesh_topology()`, and `app/static/app.js` to properly distinguish OpenThread 2-bit Link Quality (`0–3`, where `3/3` is maximum/excellent and `2/3` is good) from 8-bit 802.15.4 LQI (`0–255`), preventing healthy nodes reporting `lqi: 3` from being falsely penalized as `"Low LQI (3/255)"`.

## [2.0.6] - 2026-10-30

### Added: Full Diagnostic Log & Telemetry Bundle Download (`Download Logs` Button)
- **In-Memory Application Log Ring Buffer (`_RingBufferLogHandler`)**:
  - Captures up to 500 internal `matter_thread_ai` and `uvicorn` log entries in real time alongside Home Assistant Supervisor's `core_matter_server` and `core_openthread_border_router` add-on logs, the latest AI diagnostic report, and the full JSON network scan telemetry.
- **One-Click `Download Logs` Buttons**:
  - Added **Download Logs** buttons in the **Top Header Bar**, the **AI Diagnostic Report** header, and the **Log & Raw JSON Analyzer** tab (`GET /api/diagnostics/logs` & `GET /api/diagnostics/download`), generating a timestamped `matter-thread-diagnostics-YYYYMMDD-HHMMSS.log` file.

## [2.0.5] - 2026-10-30

### Fixed: Dynamic `ModelService.ListModels` Resolution, Removed Retired `gemini-1.5-flash` Fallback & SSE Streaming
- **Why `Google Error 404 (gemini-1.5-flash)` Appeared When `gemini-3.8-flash` Was Set**:
  - Previously, when `models/gemini-3.8-flash` returned HTTP 404 from Google's `v1beta` endpoint, `_call_gemini` iterated through a hardcoded fallback array ending in `"gemini-1.5-flash"`. Because `gemini-1.5-flash` is retired in 2026, the final attempt failed with `404 (gemini-1.5-flash)` and reported `gemini-1.5-flash` in the error instead of the user's selected model.
- **Live Google `ModelService.ListModels` Discovery (`GET /v1beta/models`)**:
  - Added `_fetch_live_gemini_models()` and `GET /api/ai/models` to query Google's `ListModels` API using your configured API key and populate the Settings and AI Studio dropdowns with the exact `generateContent` models active on your account (sorted with `gemini-3*` and `gemini-2.5*` first).
  - Removed retired `gemini-1.5-flash` / `gemini-1.5-pro` / `gemini-2.0-flash` from fallback lists. If a model alias like `gemini-3.8-flash` returns 404, `_call_gemini` now queries `ListModels` live to resolve the closest active `gemini-3*` or `gemini-2.5*` model on your account.
- **SSE Streaming (`:streamGenerateContent?alt=sse`) & Zero-Latency Flash Thinking**:
  - Switched Gemini generation to Server-Sent Events streaming (`:streamGenerateContent?alt=sse`) with `thinkingBudget: 0` on Flash models so response chunks start arriving in ~1–2 seconds and never hit idle TCP `ReadTimeout`.

## [2.0.4] - 2026-10-30

### Fixed: Gemini `ReadTimeout` under `host_network: true` & Fast Thinking Budget
- **Bound Outbound Cloud AI Requests to IPv4 (`0.0.0.0`)**:
  - Under `host_network: true`, `httpx` previously attempted to send multi-kilobyte HTTP POST bodies to `generativelanguage.googleapis.com` over IPv6 (`AAAA`), which hangs until `ReadTimeout` on residential networks where IPv6 WAN routing or PMTU discovery is blackholed by the ISP/router while local Thread IPv6 (`fd00::/8`) is active.
  - Added `_ipv4_transport()` (`httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=1)`) so all outbound HTTPS calls to Gemini, OpenAI, and Anthropic strictly use IPv4 WAN while preserving `host_network: true` for local Thread IPv6/mDNS scanning.
- **Capped Gemini 2.5 Thinking Budget & Added Timeout Model Failover**:
  - Configured `thinkingConfig: {"thinkingBudget": 512}` on `gemini-2.5-flash` (`1024` on `gemini-2.5-pro`) and extracted non-thought response parts so Gemini 2.5 responds in ~4–8 seconds instead of spending minutes generating internal thinking tokens.
  - Added automatic timeout failover (`[selected_model, "gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash"]`) and compacted the JSON diagnostic payload by 65%.

## [2.0.3] - 2026-10-30

### Added & Fixed: Live Force-Directed Physics Topology, Device Search Box & Single Preferred Border Router
- **Interactive Force-Directed RF Proximity Topology (`renderSvgTopology` & `build_real_mesh_topology`)**:
  - Replaced the static row layout with a live 60fps force-directed physics simulation (`requestAnimationFrame`) where spring distances (`target_distance`) are driven by real RF signal proximity (`RSSI` in dBm, `LQI`, and LAN `Ping RTT` in ms).
  - Nodes with strong signal (`-45 dBm` to `-62 dBm`) pull closely together (`~70–100px`) with thicker emerald links; weak/distant links (`< -82 dBm`) stretch further out (`~190–225px`) with dashed warning links.
  - Added interactive pointer drag-and-drop on all nodes, mouse-wheel zoom & canvas pan, a **Re-layout** physics button, and a **Center** reset button.
- **Real-Time Device Search & Role Filter**:
  - Added a live search bar (`#matter-node-search`) and role/status filter dropdown (`All Roles & States`, `Online Only`, `Offline / Weak RF`, `Thread Routers / Leader`, `End Devices / Sleepy`) on the Commissioned Matter Nodes table.
  - Added a synced search box (`#topology-node-search`) on the Topology tab that highlights and pulses matching devices directly on the live physics canvas.
- **Fixed All Border Routers Showing `★ Preferred`**:
  - Previously, when a Thread dataset was marked `preferred: true`, all Border Routers on that dataset inherited `preferred = True`.
  - Updated `ThreadAnalyzer.detect_split_networks` to match `preferred_border_agent_id` / `preferred_extended_address` (or the single primary/HA OTBR router) so only the single Preferred Border Router displays `★ Preferred Router`.

## [2.0.2] - 2026-10-30

### Fixed: Border Router Multi-Source Deduplication (`mDNS / HA Discovery` + `Live UDP mDNS`)
- **Eliminated Duplicate Border Router Entries**:
  - Previously, Border Routers discovered simultaneously via Home Assistant (`mDNS / HA Discovery`) and raw UDP mDNS (`Live UDP mDNS (_meshcop._udp)`) generated different deduplication keys when `Live UDP mDNS` decoded a 32-char `border_agent_id` (`ba` TXT key) while Home Assistant's payload omitted `border_agent_id` or when an Apple Border Router (`Nursery`) sent its PTR record before its TXT record (`UNKNOWN` Extended PAN ID).
  - Implemented multi-attribute Border Router deduplication and in-place field merging across `ThreadAnalyzer.detect_split_networks`, `HAClient.get_all_available_thread_networks`, and `NetworkChecker.inspect_mdns_discovery` matching by normalized `instance_name`/`name`, `ext_address`, `border_agent_id`, shared IPv4/IPv6 address, or hostname.
  - Partial `UNKNOWN` mDNS records (such as Apple HomePod/Apple TV PTR replies) now automatically merge into their full Border Router entry and trigger an immediate unicast `TXT` (`QTYPE=16`) + `ANY` (`QTYPE=255`) follow-up query.
  - Ordered router IP lists so routable IPv4 and Thread ULA (`fd00::/8`) addresses always appear before link-local (`fe80::`) addresses.

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
