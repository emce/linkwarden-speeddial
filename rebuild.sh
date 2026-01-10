#!/bin/sh

git pull
podman-compose stop
podman image prune -f
podman-compose ps -q | xargs -r podman inspect --format '{{.ImageName}}' | sort -u | xargs -r podman rmi -f || true
podman-compose build --no-cache
podman-compose up -d