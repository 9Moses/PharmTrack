#!/usr/bin/env bash
# =============================================================================
# jenkins/setup-dind.sh — PharmTrack Jenkins + Docker-in-Docker bootstrap
# =============================================================================
# Run this once from the project root to (re)create a clean DinD + Jenkins
# stack with working TLS.
#
# Usage (Windows Git Bash — recommended):
#   MSYS_NO_PATHCONV=1 bash jenkins/setup-dind.sh
#
# Usage (Linux / macOS / WSL):
#   bash jenkins/setup-dind.sh
#
# Prerequisites:
#   - Docker Desktop running
#   - pharmtrack-jenkins:latest image already built
#     (run: docker build -t pharmtrack-jenkins:latest -f jenkins/Dockerfile .)
# =============================================================================
set -euo pipefail

# ── Windows Git Bash fix ───────────────────────────────────────────────────
# Prevents Git Bash from converting /certs/... paths into Windows-style paths
# like C:/Program Files/Git/certs/... when passing them to docker commands.
export MSYS_NO_PATHCONV=1

NETWORK="pharmtrack-ci"
JENKINS_IMAGE="pharmtrack-jenkins:latest"
DIND_IMAGE="docker:25-dind"

# ── Colours ────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── 1. Tear down existing containers ──────────────────────────────────────
info "Stopping and removing old containers (jenkins, dind)..."
docker rm -f jenkins dind 2>/dev/null || true

# ── 2. Remove old cert volumes so DinD regenerates fresh certs ────────────
info "Removing stale cert volumes..."
docker volume rm dind-certs-client dind-certs-ca 2>/dev/null || true

# ── 3. Ensure network exists ───────────────────────────────────────────────
if ! docker network inspect "${NETWORK}" >/dev/null 2>&1; then
    info "Creating network '${NETWORK}'..."
    docker network create "${NETWORK}"
else
    info "Network '${NETWORK}' already exists."
fi

# ── 4. Start DinD ─────────────────────────────────────────────────────────
info "Starting DinD container..."
docker run -d \
    --name dind \
    --privileged \
    --network "${NETWORK}" \
    --network-alias dind \
    --hostname dind \
    -e DOCKER_TLS_CERTDIR=/certs \
    -v dind-certs-ca:/certs/ca \
    -v dind-certs-client:/certs/client \
    -v jenkins-docker-graph:/var/lib/docker \
    "${DIND_IMAGE}"

# ── 5. Wait for DinD to generate TLS certs ────────────────────────────────
info "Waiting for DinD to generate TLS certificates..."
MAX_WAIT=60   # seconds
WAITED=0
until docker exec dind ls /certs/client/ca.pem >/dev/null 2>&1; do
    if [ "${WAITED}" -ge "${MAX_WAIT}" ]; then
        error "DinD did not generate certs within ${MAX_WAIT}s. Check: docker logs dind"
    fi
    printf "  waiting... (%ds)\r" "${WAITED}"
    sleep 2
    WAITED=$((WAITED + 2))
done
echo ""
info "TLS certificates are ready!"
docker exec dind ls -la /certs/client/

# ── 6. Start Jenkins ───────────────────────────────────────────────────────
info "Starting Jenkins container..."
docker run -d \
    --name jenkins \
    --network "${NETWORK}" \
    -p 8080:8080 \
    -p 50000:50000 \
    -e DOCKER_HOST=tcp://dind:2376 \
    -e DOCKER_CERT_PATH=/certs/client \
    -e DOCKER_TLS_VERIFY=1 \
    -v dind-certs-client:/certs/client:ro \
    -v jenkins-data:/var/jenkins_home \
    "${JENKINS_IMAGE}"

# ── 7. Verify Jenkins can reach the Docker daemon ─────────────────────────
info "Waiting for Jenkins to start and reach the Docker daemon..."
MAX_WAIT=60
WAITED=0
until docker exec jenkins docker version >/dev/null 2>&1; do
    if [ "${WAITED}" -ge "${MAX_WAIT}" ]; then
        warn "Jenkins could not reach Docker daemon after ${MAX_WAIT}s."
        echo ""
        echo "--- jenkins container logs (last 30 lines) ---"
        docker logs jenkins --tail 30
        error "Fix the issue above and re-run this script."
    fi
    printf "  waiting... (%ds)\r" "${WAITED}"
    sleep 3
    WAITED=$((WAITED + 3))
done
echo ""
info "Jenkins can reach the Docker daemon!"

# ── 8. Final status ────────────────────────────────────────────────────────
echo ""
info "=== Final verification ==="
docker exec jenkins docker version
echo ""
docker exec jenkins kubectl version --client 2>/dev/null && \
    info "kubectl is available" || \
    warn "kubectl not found in Jenkins container (rebuild the image if needed)"

echo ""
info "=== All done! ==="
info "Jenkins UI -> http://localhost:8080"
info "To get the initial admin password:"
echo "    docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword"
