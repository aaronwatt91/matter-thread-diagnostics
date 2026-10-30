#!/usr/bin/env bash
set -e

echo "[INFO] Starting Matter & Thread AI Diagnostics Add-on (v2.0.1)..."

# When running with host_network: true on Home Assistant OS, ensure 'supervisor' and 'homeassistant'
# resolve to the Hass.io internal bridge addresses if not already in /etc/hosts or DNS.
if ! getent hosts supervisor >/dev/null 2>&1; then
    echo "[INFO] Adding '172.30.32.2 supervisor' to /etc/hosts for host_network mode..."
    echo "172.30.32.2 supervisor" >> /etc/hosts || true
fi

if ! getent hosts homeassistant >/dev/null 2>&1; then
    echo "172.30.32.1 homeassistant" >> /etc/hosts || true
fi

# Check if running inside Home Assistant OS Add-on environment
if [ -f /data/options.json ]; then
    echo "[INFO] Found /data/options.json, loading configuration from Home Assistant Supervisor..."
    export HA_OPTIONS_PATH="/data/options.json"
else
    echo "[INFO] Running in standalone/development mode (no /data/options.json)."
fi

if [ -n "${SUPERVISOR_TOKEN:-}" ]; then
    echo "[INFO] SUPERVISOR_TOKEN is present (length: ${#SUPERVISOR_TOKEN})."
elif [ -n "${HASSIO_TOKEN:-}" ]; then
    echo "[INFO] Using HASSIO_TOKEN as SUPERVISOR_TOKEN."
    export SUPERVISOR_TOKEN="${HASSIO_TOKEN}"
else
    echo "[WARN] Neither SUPERVISOR_TOKEN nor HASSIO_TOKEN is set in environment!"
fi

cd /app

echo "[INFO] Launching Uvicorn on 0.0.0.0:8099..."
exec python3 -m uvicorn main:app --host 0.0.0.0 --port 8099 --log-level info
