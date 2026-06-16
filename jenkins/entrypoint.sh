#!/bin/bash
set -e

# Dynamically match the docker group GID to the mounted socket's GID.
# This is needed because Docker Desktop on Windows/Linux may use a different GID
# than the 999 baked into the image at build time.
if [ -S /var/run/docker.sock ]; then
    SOCK_GID=$(stat -c '%g' /var/run/docker.sock)
    echo "[entrypoint] Docker socket GID on host: ${SOCK_GID}"

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
    echo "[entrypoint] WARNING: /var/run/docker.sock not found — Docker builds will fail."
fi

# Hand off to the official Jenkins entrypoint as the jenkins user
exec gosu jenkins /usr/bin/tini -- /usr/local/bin/jenkins.sh "$@"
