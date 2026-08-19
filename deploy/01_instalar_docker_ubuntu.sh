#!/usr/bin/env bash
set -euo pipefail
if command -v docker >/dev/null 2>&1; then
  echo "Docker ya está instalado."
  docker --version || true
  exit 0
fi
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER" || true
echo "Docker instalado. Cerrá y volvé a abrir la sesión SSH para aplicar el grupo docker."
