#!/usr/bin/env bash
# Local (no-Docker) ClipScribe stack for Linux.
# Starts: Postgres (port 5544) -> Flask API (5001) -> worker -> Next.js (3000).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
export DATABASE_URL="postgresql://clipscribe:clipscribe-local@127.0.0.1:5544/clipscribe"
export CLIPSCRIBE_UPLOADS_DIR="$ROOT/.cache/uploads"
export CLIPSCRIBE_CACHE_DIR="$ROOT/.cache"
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy NODE_USE_ENV_PROXY no_proxy NO_PROXY || true
mkdir -p "$ROOT/.cache/uploads"

"$ROOT/.venv/bin/python" "$ROOT/scripts-local-pg.py" 2>/dev/null | grep -E "^(postgres|starting|creating|DATABASE_URL)" || true

if ! curl -sf -m 2 --noproxy '*' http://127.0.0.1:5001/health >/dev/null; then
  setsid -f "$ROOT/.venv/bin/python" "$ROOT/backend/app.py" </dev/null >>/tmp/clipscribe-api.log 2>&1
  echo "api: starting (log /tmp/clipscribe-api.log)"
else
  echo "api: already running"
fi

if ! pgrep -f "backend/worker.py" >/dev/null; then
  setsid -f env DATABASE_URL="$DATABASE_URL" CLIPSCRIBE_UPLOADS_DIR="$CLIPSCRIBE_UPLOADS_DIR" \
    CLIPSCRIBE_CACHE_DIR="$CLIPSCRIBE_CACHE_DIR" "$ROOT/.venv/bin/python" "$ROOT/backend/worker.py" \
    </dev/null >>/tmp/clipscribe-worker.log 2>&1
  echo "worker: starting (log /tmp/clipscribe-worker.log)"
else
  echo "worker: already running"
fi

if ! curl -sf -m 2 --noproxy '*' http://127.0.0.1:3000 >/dev/null; then
  (cd "$ROOT/frontend" && setsid -f npm run dev -- -p 3000 </dev/null >>/tmp/clipscribe-web.log 2>&1)
  echo "web: starting (log /tmp/clipscribe-web.log)"
else
  echo "web: already running"
fi
