#!/bin/bash
set -e

# ── Docker connectivity setup ──────────────────────────────────────────────
# Two modes are supported:
#
#   Mode A — Unix socket (Docker Desktop / rootful Docker on Linux)
#             DOCKER_HOST is unset or set to unix:///var/run/docker.sock
#             The socket is bind-mounted at /var/run/docker.sock
#
#   Mode B — TCP + TLS (Docker-in-Docker)
#             DOCKER_HOST=tcp://dind:2376
#             DOCKER_TLS_VERIFY=1
#             DOCKER_CERT_PATH=/certs/client   (volume-mounted from dind)
#
# In Mode B there is no socket to fix up, so we skip that block entirely.

if [ -n "${DOCKER_HOST:-}" ] && echo "${DOCKER_HOST}" | grep -q "^tcp://"; then
    echo "[entrypoint] TCP/TLS mode detected (DOCKER_HOST=${DOCKER_HOST})"
    echo "[entrypoint] Skipping socket GID fixup — using DinD over TLS."
elif [ -S /var/run/docker.sock ]; then
    SOCK_GID=$(stat -c '%g' /var/run/docker.sock)
    echo "[entrypoint] Unix socket mode — Docker socket GID on host: ${SOCK_GID}"

    # Reassign the docker group to the socket's actual GID
    if getent group docker > /dev/null 2>&1; then
        groupmod -g "${SOCK_GID}" docker 2>/dev/null || true
    else
        groupadd -g "${SOCK_GID}" docker
    fi

    # Make sure jenkins user is in the group
    usermod -aG docker jenkins 2>/dev/null || true

    # Ensure socket is group-readable/writable
    chmod 660 /var/run/docker.sock || true
    chown root:docker /var/run/docker.sock || true
else
    echo "[entrypoint] WARNING: No Docker socket found and DOCKER_HOST is not a TCP address."
    echo "[entrypoint] Docker builds will fail unless DOCKER_HOST is set correctly."
fi

# Hand off to the official Jenkins entrypoint as the jenkins user
exec gosu jenkins /usr/bin/tini -- /usr/local/bin/jenkins.sh "$@"
