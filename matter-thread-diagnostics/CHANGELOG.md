# Changelog

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
