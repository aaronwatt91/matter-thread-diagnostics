# Changelog

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
