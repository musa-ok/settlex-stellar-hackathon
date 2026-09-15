#!/usr/bin/env bash
# Kasa AI — local demo helpers
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

case "${1:-}" in
  backend)
    cd "$ROOT/backend"
    source .venv/bin/activate
    exec uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
    ;;
  frontend)
    cd "$ROOT/frontend"
    exec npm run dev -- --host 127.0.0.1 --port 5173
    ;;
  *)
    echo "Usage: $0 {backend|frontend}"
    exit 1
    ;;
esac
