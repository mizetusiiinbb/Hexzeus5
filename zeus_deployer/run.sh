#!/bin/sh
set -e

PORT="${PORT:-8080}"
echo "[*] Launching ZEUS Polymorphic Custom Deployer on http://0.0.0.0:${PORT} ..."
exec python3 -m uvicorn zeus_deployer.server:app --host 0.0.0.0 --port "${PORT}"
