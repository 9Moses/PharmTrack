FROM jenkins/jenkins:lts

USER root

# Install Docker CLI + gosu (for privilege drop in entrypoint)
RUN apt-get update \
  && apt-get install -y ca-certificates curl gnupg lsb-release apt-transport-https gosu \
  && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
  && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list \
  && apt-get update \
  && apt-get install -y --no-install-recommends docker-ce-cli \
  && rm -rf /var/lib/apt/lists/*

# Install Docker Pipeline plugin so Declarative docker agent works
RUN jenkins-plugin-cli --plugins docker-workflow

# Pre-create docker group (GID will be corrected at runtime by entrypoint)
RUN groupadd -f -g 999 docker \
  && usermod -aG docker jenkins

# Copy and register the runtime entrypoint
COPY jenkins/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Run entrypoint as root so it can fix GID, then drops to jenkins via gosu
ENTRYPOINT ["/entrypoint.sh"]
