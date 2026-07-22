#!/usr/bin/env bash
# Stable MacBook → Mac Studio hub path when LAN :8000 is flaky.
# Usage: ./scripts/hub-tunnel.sh [studio-host]
set -euo pipefail
HOST="${1:-socials@192.168.0.183}"
LOCAL_PORT="${HUB_TUNNEL_PORT:-18000}"
pkill -f "ssh.*-L ${LOCAL_PORT}:127.0.0.1:8000" 2>/dev/null || true
sleep 0.3
ssh -o BatchMode=yes -o ConnectTimeout=8 \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -f -N -L "${LOCAL_PORT}:127.0.0.1:8000" "$HOST"
curl -sf "http://127.0.0.1:${LOCAL_PORT}/health" >/dev/null
echo "Hub tunnel OK → http://127.0.0.1:${LOCAL_PORT}  (set HUB_PROXY_TARGET to this)"
echo "Example: HUB_PROXY_TARGET=http://127.0.0.1:${LOCAL_PORT} npm run dev-server"
