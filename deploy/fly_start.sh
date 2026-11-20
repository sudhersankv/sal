#!/usr/bin/env bash
# Sal on Fly: one machine runs every service. Only the dashboard (:8080) is public; /mcp is proxied to :8103.
set -u
cd /app
keep() { while true; do "$@"; echo "[fly_start] '$*' exited ($?), restarting in 2s" >&2; sleep 2; done; }

python -m seed || echo "[fly_start] seed failed, continuing" >&2
# Airbyte OSS: sync the shop sheets with the official source-file connector (isolated py3.11 env via uvx)
(python -m tools.integrations.airbyte_oss sync || echo "[fly_start] airbyte sync failed" >&2) &

keep python -m uvicorn vendors.app:app --host 127.0.0.1 --port 8101 &
keep python -m uvicorn sim.api:app --host 127.0.0.1 --port 8102 &
keep python -m agent.mcp_public --http --host 127.0.0.1 --port 8103 &
if [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then keep python -m agent.telegram_bot & fi

exec python -m uvicorn ui.server.app:app --host 0.0.0.0 --port 8080 --proxy-headers --forwarded-allow-ips '*'
