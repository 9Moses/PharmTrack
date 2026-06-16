#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME=custom-jenkins:latest
DOCKERFILE_PATH=jenkins/Dockerfile

echo "Building ${IMAGE_NAME} from ${DOCKERFILE_PATH}..."
docker build -t ${IMAGE_NAME} -f ${DOCKERFILE_PATH} .

echo "Running container 'jenkins' (will stop and remove existing)..."
docker rm -f jenkins 2>/dev/null || true

docker run -d --name jenkins \
  -p 8080:8080 -p 50000:50000 \
  -v jenkins_home:/var/jenkins_home \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "/c/Users/TECH GIANTS PLUS/.kube:/root/.kube:ro" \
  ${IMAGE_NAME}

echo "Jenkins started. Visit http://localhost:8080"
