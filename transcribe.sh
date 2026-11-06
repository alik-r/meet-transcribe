#!/usr/bin/env bash
# Runs transcribe.py in Docker. The project is mounted at its own path, so paths
# printed by the script are valid on the host and files stay owned by this user.
set -e
root="$(dirname "$(readlink -f "$0")")"

if ! docker image inspect meet-transcribe > /dev/null 2>&1; then
    echo "Building Docker image (first run takes a few minutes)..."
fi
docker build --quiet --tag meet-transcribe "$root" > /dev/null
exec docker run --rm --init \
    --user "$(id -u):$(id -g)" \
    --volume "$root:$root" \
    --workdir "$root" \
    meet-transcribe python transcribe.py "$@"
