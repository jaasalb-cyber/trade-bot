#!/usr/bin/env bash

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="${FT_BRANCH:-stable}"
REMOTE="${FT_REMOTE:-origin}"

cd "$REPO_DIR"

if ! command -v docker >/dev/null 2>&1; then
    echo "docker is required but was not found in PATH" >&2
    exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
    echo "docker compose plugin is required but was not found" >&2
    exit 1
fi

if [[ ! -f user_data/config.json ]]; then
    echo "Missing user_data/config.json. Create and configure it before starting the bot." >&2
    exit 1
fi

echo "Fetching latest git metadata from ${REMOTE}/${BRANCH}..."
git fetch "$REMOTE" "$BRANCH"

echo "Pulling latest code..."
git pull --ff-only "$REMOTE" "$BRANCH"

echo "Pulling latest freqtrade image..."
docker compose pull

echo "Starting freqtrade..."
exec docker compose up -d
