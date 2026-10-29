#!/usr/bin/env bash
set -e

echo "[INFO] Starting Matter & Thread AI Diagnostics Add-on..."

# Check if running inside Home Assistant OS Add-on environment
if [ -f /data/options.json ]; then
    echo "[INFO] Found /data/options.json, loading configuration from Home Assistant Supervisor..."
    export HA_OPTIONS_PATH="/data/options.json"
else
    echo "[INFO] Running in standalone/development mode (no /data/options.json)."
fi

# Run the FastAPI app using Uvicorn on 0.0.0.0:8099 (HA Ingress port)
exec python3 -m uvicorn main:app --host 0.0.0.0 --port 8099 --log-level info
