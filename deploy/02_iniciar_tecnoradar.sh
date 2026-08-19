#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then
  cp deploy/.env.example .env
  echo "Creado .env desde deploy/.env.example. Editá DOMAIN y volvé a ejecutar este script."
  exit 1
fi
docker compose -f docker-compose.public.yml --env-file .env up -d --build
