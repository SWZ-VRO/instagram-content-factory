#!/usr/bin/env bash
# One-command launcher (macOS/Linux/WSL/Git Bash). From this folder: ./run.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if [ ! -f .env ]; then
  echo "No .env found -- copying .env.example to .env. Edit it (SECRET_KEY at minimum) before connecting real Instagram accounts."
  cp .env.example .env
fi

echo "Starting Instagram Content Factory (docker compose up -d --build)..."
docker compose up -d --build

echo "Waiting for the backend to become healthy..."
for i in $(seq 1 60); do
  if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "Backend is up."
    break
  fi
  sleep 2
  if [ "$i" -eq 60 ]; then
    echo "Backend did not become healthy in time -- check logs with: docker compose logs backend"
    exit 1
  fi
done

echo "Dashboard : http://localhost:3000"
echo "API docs  : http://localhost:8000/docs"
echo "Stop with : docker compose down"

# Best-effort browser open, ignored if no GUI (headless server/WSL without a browser bridge).
( command -v open >/dev/null 2>&1 && open http://localhost:3000 ) || \
( command -v xdg-open >/dev/null 2>&1 && xdg-open http://localhost:3000 ) || true
