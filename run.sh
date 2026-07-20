#!/usr/bin/env bash
# Build the frontend (if needed) and serve everything from one port.
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8787}"

if [ ! -d .venv ]; then
	python3 -m venv .venv
	.venv/bin/pip install -q -r backend/requirements.txt
fi

if [ "${SKIP_BUILD:-}" != "1" ]; then
	(cd frontend && [ -d node_modules ] || npm install)
	(cd frontend && npm run build)
fi

echo "→ http://localhost:${PORT}"
exec .venv/bin/python -m uvicorn backend.app.main:app --port "${PORT}"
