# ============================================================================
# jenkins/Dockerfile — PharmTrack Jenkins Controller
# ============================================================================
# Designed to run alongside a separate Docker-in-Docker (dind) container.
# This image does NOT run a Docker daemon itself — it only has the Docker
# CLI + kubectl + helm + ansible + terraform, and talks to the dind
# container over the network via DOCKER_HOST (set at `docker run` time,
# see RUN_JENKINS.md / the run command below).
# ============================================================================

FROM jenkins/jenkins:lts

USER root

# ── Base tools ────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    apt-transport-https \
    unzip \
    git \
    python3 \
    python3-pip \
    python3-venv \
    gosu \
    jq \
    wget \
    && rm -rf /var/lib/apt/lists/*

# ── Docker CLI only (daemon lives in the separate dind container) ──────────
RUN curl -fsSL https://download.docker.com/linux/debian/gpg \
        | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# ── kubectl ───────────────────────────────────────────────────────────────
# Pinned version instead of "stable.txt" — avoids silent breakage when
# a new K8s release ships and changes client/server skew assumptions.
ARG KUBECTL_VERSION=v1.31.0
RUN set -eux; \
    wget -q -O /usr/local/bin/kubectl \
        "https://storage.googleapis.com/kubernetes-release/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl"; \
    wget -q -O /tmp/kubectl.sha256 \
        "https://storage.googleapis.com/kubernetes-release/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl.sha256"; \
    # Verify — build FAILS here if checksum doesn't match
    EXPECTED=$(cat /tmp/kubectl.sha256); \
    ACTUAL=$(sha256sum /usr/local/bin/kubectl | awk '{print $1}'); \
    [ "$EXPECTED" = "$ACTUAL" ] || exit 1; \
    chmod +x /usr/local/bin/kubectl

# ── Helm (needed by Ansible roles that call `helm upgrade --install`) ───────
ARG HELM_VERSION=v3.14.4
RUN curl -fsSL "https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz" -o helm.tar.gz \
    && tar -zxvf helm.tar.gz \
    && mv linux-amd64/helm /usr/local/bin/helm \
    && rm -rf helm.tar.gz linux-amd64 \
    && helm version

# ── Terraform ─────────────────────────────────────────────────────────────
ARG TERRAFORM_VERSION=1.7.5
RUN curl -fsSLO "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip" \
    && unzip terraform_${TERRAFORM_VERSION}_linux_amd64.zip -d /usr/local/bin \
    && rm terraform_${TERRAFORM_VERSION}_linux_amd64.zip \
    && terraform -version

# ── AWS CLI v2 (used by `aws eks update-kubeconfig` in Ansible) ─────────────
# RUN curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip \
#     && unzip -q awscliv2.zip \
#     && ./aws/install \
#     && rm -rf awscliv2.zip aws \
#     && aws --version

# ── Ansible (controller runs playbooks locally — see infrastructure/ansible) ─
RUN pip3 install --no-cache-dir --break-system-packages \
        --timeout 120 --retries 10 --resume-retries 5 \
        ansible==9.4.0

# ── Jenkins plugins ───────────────────────────────────────────────────────
# docker-workflow:        docker.image()/docker.build() pipeline steps
# pipeline-utility-steps: readJSON/readYaml etc., used by some pipelines
# git / github / workflow-aggregator: core pipeline + SCM support
# credentials-binding:    withCredentials / credentials() bindings
# blueocean:               optional UI, comment out to slim the image
RUN jenkins-plugin-cli --plugins \
    "docker-workflow" \
    "pipeline-utility-steps" \
    "git" \
    "github" \
    "workflow-aggregator" \
    "credentials-binding" \
    "ansicolor" \
    "timestamper" \
    "ws-cleanup"

# ── Docker group so the jenkins user can use the CLI against dind ──────────
# GID 999 may already be taken on some base image variants — fall back to
# whatever GID the 'docker' group already has, or let the system pick one.
RUN if getent group docker >/dev/null; then \
        usermod -aG docker jenkins; \
    elif getent group 999 >/dev/null; then \
        groupadd docker && usermod -aG docker jenkins; \
    else \
        groupadd -g 999 docker && usermod -aG docker jenkins; \
    fi

# ── Pre-create the kubeconfig mount point used by pipelines ────────────────
RUN mkdir -p /var/jenkins_home/.kube && chown -R jenkins:jenkins /var/jenkins_home/.kube

USER jenkins
