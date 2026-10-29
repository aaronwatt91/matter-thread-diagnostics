# Matter & Thread AI Diagnostics for Home Assistant Green

[![Home Assistant Add-on](https://img.shields.io/badge/Home%20Assistant-Add--on-blue.svg)](https://www.home-assistant.io)
[![Supports aarch64](https://img.shields.io/badge/arch-aarch64-green.svg)](https://www.home-assistant.io/green/)
[![HA Ingress](https://img.shields.io/badge/Ingress-Supported-brightgreen.svg)](https://www.home-assistant.io)

An AI-powered diagnostic and troubleshooting application for **Home Assistant Green**, resolving intermittent connectivity, commissioning timeouts, and mesh desynchronization across Matter-over-Thread devices.

---

## 🌟 Why this exists

Matter-over-Thread offers seamless smart home interoperability, but in multi-ecosystem homes (Apple Home, Google Home, Home Assistant Green with SkyConnect/Connect ZBT-1), troubleshooting failures is notoriously difficult:
- **Split Networks**: Apple TV/HomePod and Home Assistant operate on separate Thread meshes without warning.
- **RF Interference**: Thread channels 11–24 overlap with 2.4 GHz Wi-Fi channels 1, 6, and 11.
- **Missing IPv6 Routes**: Wi-Fi switches drop ICMPv6 Route Information Options (RIO), preventing HA Green from routing packets to `fd00::/8` Thread devices.
- **Intermittently Connected Devices (ICD)**: Battery sensors drop offline when parent routers prune child tables.

This Add-on combines **deterministic network inspection rules** with **Cloud AI (Google Gemini, OpenAI GPT-4o, Anthropic Claude)** to diagnose your exact network topology and give you step-by-step remediation instructions.

---

## 🛠️ Architecture

```
+-----------------------------------------------------------------+
|                      Home Assistant Green                       |
|                                                                 |
|  +--------------------+         +----------------------------+  |
|  |  Matter Server     | <=====> |  Matter & Thread AI        |  |
|  |  (WebSocket :5580) |         |  Diagnostics Add-on        |  |
|  +--------------------+         |  - Thread Analyzer         |  |
|                                 |  - RF Coexistence Check    |  |
|  +--------------------+         |  - IPv6 Routing Inspector  |  |
|  |  OpenThread Router | <=====> |  - Ingress Web UI (:8099)  |  |
|  |  (REST API :8081)  |         +--------------+-------------+  |
|  +--------------------+                        |                |
|                                                |                |
+------------------------------------------------|----------------+
                                                 | HTTPS API
                                                 v
                               +----------------------------------+
                               |     Cloud AI Diagnostic API      |
                               |  - Google Gemini 2.0 Flash / Pro |
                               |  - OpenAI GPT-4o / GPT-4o-mini   |
                               |  - Anthropic Claude 3.5 Sonnet   |
                               +----------------------------------+
```

---

## 🚀 Quick Install on Home Assistant Green

1. Go to **Settings** → **Add-ons** → **Add-on Store** in Home Assistant.
2. In the top right menu **(⋮)**, click **Repositories** and add your repository URL (or drop this folder into `/addons/matter-thread-diagnostics` via Samba/SSH).
3. Find **Matter & Thread AI Diagnostics**, click **Install**, enable **Show in sidebar**, and click **Start**.
4. Open the Add-on from your Home Assistant sidebar, choose your AI provider (Google Gemini, OpenAI, or Anthropic), enter your API key, and click **Run AI Diagnosis**.

For in-depth setup instructions, see [DOCS.md](matter-thread-diagnostics/DOCS.md).
