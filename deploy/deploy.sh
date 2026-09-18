#!/usr/bin/env bash
# Deploy partition-player to the "main" server (ssh alias from ~/.ssh/config).
#
#   deploy/deploy.sh            # sync, build on the server, (re)start, install the Caddy site, smoke test
#   deploy/deploy.sh --no-build # sync and restart without rebuilding the image
#
# The image is built natively on the server (aarch64): the Python deps are wheels and the
# frontend build is a minute or two on its 2 cores. Data lives in the partition-player_data volume.
set -euo pipefail

HOST=${DEPLOY_HOST:-main}
REMOTE_DIR=${DEPLOY_DIR:-partition-player}
DOMAIN=partition-player.92.5.91.253.sslip.io
BUILD=1
[[ "${1:-}" == "--no-build" ]] && BUILD=0

cd "$(dirname "$0")/.."

echo "== syncing sources to $HOST:$REMOTE_DIR"
rsync -az --delete \
  --exclude '.git' --exclude '.venv*' --exclude 'node_modules' --exclude 'dist' \
  --exclude 'data' --exclude 'data-server.log' --exclude 'bench/out' --exclude '__pycache__' \
  --exclude '.pytest_cache' --exclude '*.out' \
  ./ "$HOST:$REMOTE_DIR/"

echo "== building and starting on $HOST"
ssh "$HOST" bash -s "$REMOTE_DIR" "$BUILD" <<'REMOTE'
set -euo pipefail
cd "$1"
if [[ "$2" == "1" ]]; then
  docker compose -f deploy/compose.yaml build
fi
docker compose -f deploy/compose.yaml up -d
# Caddy site: copy only when it changed, then reload the running Caddy.
if ! cmp -s deploy/partition-player.caddy ~/caddy-sites/partition-player.caddy; then
  cp deploy/partition-player.caddy ~/caddy-sites/partition-player.caddy
  docker exec philou-web caddy reload --config /etc/caddy/Caddyfile
  echo "caddy site installed and reloaded"
fi
docker image prune -f >/dev/null
REMOTE

echo "== waiting for the app"
for i in $(seq 1 30); do
  if ssh "$HOST" "docker exec partition-player python -c \"import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).read().decode())\"" 2>/dev/null; then
    break
  fi
  sleep 2
done

echo "== through Caddy: https://$DOMAIN/api/health"
curl -fsS --max-time 20 "https://$DOMAIN/api/health" && echo

echo "== memory on the host"
ssh "$HOST" 'free -m | head -2; docker stats --no-stream --format "{{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}"'
