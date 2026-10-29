# Matter & Thread AI Diagnostics for Home Assistant Green

An AI-powered diagnostic and troubleshooting application specifically designed to run on **Home Assistant Green** (HAOS). It analyzes Thread mesh topology, Border Router synchronization, 2.4 GHz Wi-Fi interference, IPv6 routing (ULA/RIO), and Matter server session stability to diagnose and resolve intermittent connectivity issues.

---

## 🚀 Key Capabilities

- **Automatic Multi-Border Router Synchronization Check**:
  Detects split Thread networks where Apple TV 4K / HomePod mini, Google Nest Hub, and Home Assistant (SkyConnect/Connect ZBT-1) operate on different Extended PAN IDs or Network Keys.
- **RF Coexistence & Interference Analysis**:
  Evaluates Thread 802.15.4 channels (11–26) against 2.4 GHz Wi-Fi channels (1, 6, 11) to identify channel overlap and packet loss.
- **IPv6 ULA & RIO Route Verification**:
  Inspects whether Home Assistant Green's Linux kernel has an active route to the Thread Unique Local Address prefix (`fd00::/8`) and detects multicast/mDNS filtering on Wi-Fi routers (UniFi, Omada, Eero, Asus).
- **Interactive Mesh Topology Map**:
  Visualizes Border Routers, Leader Routers, Mains-Powered Routers, and Sleepy Battery End Devices with live signal strength (LQI / RSSI) and link health.
- **Cloud AI Diagnostic Engine**:
  Synthesizes complete telemetry into structured, step-by-step troubleshooting recommendations using your choice of **Google Gemini**, **Anthropic Claude**, or **OpenAI**.
- **Native Ingress Integration**:
  Runs directly inside the Home Assistant sidebar with a sleek, dark-mode native dashboard.

---

## 📦 Installation on Home Assistant Green

### Method A: Install via Add-on Repository (Recommended)

1. In Home Assistant, navigate to **Settings** → **Add-ons** → **Add-on Store**.
2. Click the three dots **(⋮)** in the top right corner and select **Repositories**.
3. Add the repository URL:
   ```text
   https://github.com/aaronwatt/ha-matter-thread-diagnostics
   ```
4. Click **Add**, then close the dialog.
5. In the Add-on Store list, find **Matter & Thread AI Diagnostics** and click **Install**.
6. Toggle **Show in sidebar** and **Start on boot**, then click **Start**.
7. Click **Open Web UI** to access the dashboard!

### Method B: Install via Local Add-ons Directory

1. Install the **Samba Share** or **SSH & Web Terminal** add-on in Home Assistant.
2. Copy the `matter-thread-diagnostics` directory into the `/addons/` folder on your Home Assistant Green:
   ```text
   /addons/matter-thread-diagnostics/
   ```
3. Navigate to **Settings** → **Add-ons** → **Add-on Store** → Top right **(⋮)** → **Check for updates**.
4. Scroll down to the **Local add-ons** section and click **Matter & Thread AI Diagnostics**.
5. Click **Install**, enable **Show in sidebar**, and click **Start**.

---

## ⚙️ Configuration Options

Open the **Configuration** tab in the add-on settings or configure directly in the Web UI:

| Option | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `ai_provider` | list | `gemini` | `gemini` (Google Gemini), `openai`, or `anthropic` |
| `ai_model` | string | `gemini-2.0-flash` | The specific model to use (e.g. `gemini-2.0-flash`, `gpt-4o`, `claude-3-5-sonnet-20241022`) |
| `gemini_api_key` | password | `""` | Google Gemini API key ([Get one free at Google AI Studio](https://aistudio.google.com/)) |
| `openai_api_key` | password | `""` | OpenAI API key ([OpenAI Platform](https://platform.openai.com/)) |
| `anthropic_api_key` | password | `""` | Anthropic API key ([Anthropic Console](https://console.anthropic.com/)) |
| `matter_server_url` | string | `ws://core-matter-server:5580/ws` | WebSocket URL to python-matter-server add-on |
| `otbr_url` | string | `http://core-openthread-border-router:8081` | OpenThread Border Router REST API URL |

---

## 🔍 Common Matter-over-Thread Issues Solved

### 1. Split Thread Networks (The #1 Matter Interop Issue)
- **Problem**: You pair a device through an iPhone and it joins Apple's Thread network. Later, Home Assistant cannot communicate with it or it takes 15 seconds to respond.
- **Diagnosis**: The add-on flags differing Extended PAN IDs between Apple TV/HomePod and Home Assistant SkyConnect.
- **Fix**: Synchronize Thread datasets in **Settings** → **Devices & Services** → **Thread** → Choose your preferred network and sync credentials.

### 2. Wi-Fi 2.4GHz Overlap with Thread Channels
- **Problem**: Thread devices randomly drop offline or fail the CASE cryptographic handshake.
- **Diagnosis**: The add-on detects that Thread is operating on Channel 11, which directly overlaps with your 2.4GHz Wi-Fi Channel 1.
- **Fix**: Move Thread to **Channel 25** (the clean channel immune to standard Wi-Fi channels 1, 6, and 11).

### 3. Missing IPv6 Route to Thread ULA Prefix (`fd00::/8`)
- **Problem**: Home Assistant cannot ping or reach Thread devices even though Thread reports connected.
- **Diagnosis**: The add-on runs `ip -6 route` inspection and detects no route advertised via ICMPv6 Route Information Options (RIO).
- **Fix**: Enable **Multicast DNS (mDNS)**, disable "Block LAN to WLAN Multicast", and ensure **IGMP/MLD Snooping** has a querier enabled on your Wi-Fi router (UniFi/Omada/Asus).

### 4. USB 3.0 RF Interference on Home Assistant Green
- **Tip**: Always plug your SkyConnect or Thread radio into a **1-meter USB 2.0 extension cable** away from the HA Green chassis and power supply. USB 3.0 ports generate wideband RF noise directly across the 2.4 GHz spectrum.
