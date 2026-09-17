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
  all)
    echo "🚀 Starting Kasa AI (Backend + Frontend)..."
    cd "$ROOT/backend"
    source .venv/bin/activate
    uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 &
    BACKEND_PID=$!
    cd "$ROOT/frontend"
    npm run dev -- --host 127.0.0.1 --port 5173 &
    FRONTEND_PID=$!
    echo "✅ Backend: http://127.0.0.1:8000"
    echo "✅ Frontend: http://127.0.0.1:5173"
    echo "📝 Press Ctrl+C to stop both servers"
    wait $BACKEND_PID $FRONTEND_PID
    ;;
  *)
    echo "Usage: $0 {backend|frontend|all}"
    exit 1
    ;;
esac
