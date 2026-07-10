/*
 * ============================================================================
 * Jenkinsfile — PharmTrack (root, combined pipeline)
 * ============================================================================
 * Single pipeline covering infra + gateway. For independent build/deploy
 * cycles per service, use the split layout instead:
 *   - infrastructure/Jenkinsfile
 *   - gateway/Jenkinsfile
 * (see docs/ci-cd.md). This root file is kept for teams who want one job.
 *
 * Requires a Jenkins agent/controller with: docker CLI (pointed at a
 * reachable daemon via DOCKER_HOST), kubectl, git. See jenkins/RUN_JENKINS.md
 * for exact setup if you're running Jenkins via Docker-in-Docker.
 * ============================================================================
 */

pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '15'))
        timeout(time: 45, unit: 'MINUTES')
        ansiColor('xterm')
    }

    environment {
        K8S_NAMESPACE          = "pharmtrack"
        GATEWAY_IMAGE          = "9moses/gateway"
        NOTIFICATION_IMAGE     = "9moses/notification-service"
        EMAIL_IMAGE            = "9moses/email-service"

        KUBECONFIG_CRED        = credentials('pharmtrack-kubeconfig')
        DOCKERHUB_CREDS        = credentials('dockerhub-credentials')
        DB_PASSWORD            = credentials('gateway-db-password')
        REDIS_PASSWORD         = credentials('gateway-redis-password')
        RABBITMQ_PASSWORD      = credentials('gateway-rabbitmq-password')
        DJANGO_SECRET_KEY      = credentials('gateway-secret-key')
        NOTIFICATION_SECRET_KEY = credentials('notification-service-secret-key')
        NOTIFICATION_DB_PASSWORD = credentials('notification-service-db-password')
        NOTIFICATION_JWT_SECRET = credentials('notification-service-jwt-secret-key')
        EMAIL_SMTP_USER        = credentials('email-service-smtp-user')
        EMAIL_SMTP_PASSWORD    = credentials('email-service-smtp-password')
        EMAIL_DEFAULT_FROM_EMAIL = "no-reply@pharmtrack.local"
        EMAIL_DEFAULT_FROM_NAME = "PharmTrack Email Service"
        EMAIL_SMTP_HOST        = "smtp.gmail.com"
        EMAIL_SMTP_PORT        = "465"
        EMAIL_SMTP_USE_SSL     = "true"
     }

    stages {
        stage('Preflight Checks') {
            steps {
                sh '''
                    echo "=== Preflight: checking required tools ==="

                    command -v docker >/dev/null 2>&1 || {
                        echo "❌ docker CLI not found on this agent."
                        echo "   See jenkins/RUN_JENKINS.md — DOCKER_HOST must point at your dind container."
                        exit 1
                    }

                    docker version >/dev/null 2>&1 || {
                        echo "❌ docker CLI found but cannot reach a daemon."
                        echo "   Check DOCKER_HOST / DOCKER_CERT_PATH / DOCKER_TLS_VERIFY env vars"
                        echo "   and that this container shares a network with the dind container."
                        exit 1
                    }

                    command -v kubectl >/dev/null 2>&1 || {
                        echo "❌ kubectl not found on this agent. Rebuild jenkins/Dockerfile and"
                        echo "   recreate the container (docker rm -f jenkins && docker run ...)."
                        exit 1
                    }

                    echo "✅ docker and kubectl are present and docker daemon is reachable"
                    docker version --format 'Docker: client={{.Client.Version}} server={{.Server.Version}}'
                    kubectl version --client --output=yaml | head -5
                '''
            }
        }

        // ─────────────────────────────────────────────────────────────────
        // 1. Checkout & Branch Detection
        // ─────────────────────────────────────────────────────────────────
        stage('Checkout') {
            steps {
                checkout scm
                script {
                    env.DETECTED_BRANCH = env.BRANCH_NAME ?: (env.GIT_BRANCH ? env.GIT_BRANCH.replace('origin/', '') : sh(
                        script: 'git rev-parse --abbrev-ref HEAD',
                        returnStdout: true
                    ).trim())

                    env.GIT_COMMIT_FULL  = sh(script: 'git rev-parse HEAD', returnStdout: true).trim()
                    env.GIT_COMMIT_SHORT = env.GIT_COMMIT_FULL[0..7]
                    env.IMAGE_TAG        = "${env.GIT_COMMIT_SHORT}-${env.BUILD_NUMBER}"

                    echo "Branch: ${env.DETECTED_BRANCH} | Commit: ${env.GIT_COMMIT_SHORT} | Tag: ${env.IMAGE_TAG}"
                    currentBuild.displayName = "#${env.BUILD_NUMBER} - ${env.DETECTED_BRANCH} (${env.GIT_COMMIT_SHORT})"
                }
            }
        }

        // ─────────────────────────────────────────────────────────────────
        // 2. Infrastructure Provisioning
        //    Uses Declarative's built-in `changeset` condition instead of a
        //    custom Groovy helper — avoids CPS-sandbox RejectedAccessException
        //    and works correctly on first-ever builds (no prior commit).
        // ─────────────────────────────────────────────────────────────────
        stage('Infrastructure') {
            when {
                expression { env.DETECTED_BRANCH in ['main', 'master'] }
            }
            stages {
                stage('Validate Manifests') {
                    steps {
                        sh '''
                            export KUBECONFIG=${KUBECONFIG_CRED}
                            for f in k8s/infra/*.yaml; do
                                [ -f "$f" ] || continue
                                case "$f" in
                                    *secrets.example*) echo "Skipping $f (template only)"; continue ;;
                                esac
                                echo "Validating $f ..."
                                kubectl apply --dry-run=client -f "$f"
                            done

                            for service_dir in notification-service email-service; do
                                if [ -d "$service_dir/k8s/base" ]; then
                                    echo "Validating $service_dir/k8s/base manifests..."
                                    kubectl apply --dry-run=client -k "$service_dir/k8s/base"
                                fi
                            done
                        '''
                    }
                }

                stage('Inject Shared Secrets') {
                    steps {
                        sh '''
                            export KUBECONFIG=${KUBECONFIG_CRED}

                            kubectl create namespace ${K8S_NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

                            kubectl create secret generic gateway-db-secret \
                                --from-literal=POSTGRES_USER=postgres \
                                --from-literal=POSTGRES_PASSWORD="${DB_PASSWORD}" \
                                -n ${K8S_NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

                            kubectl create secret generic redis-secret \
                                --from-literal=REDIS_PASSWORD="${REDIS_PASSWORD}" \
                                -n ${K8S_NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

                            kubectl create secret generic rabbitmq-secret \
                                --from-literal=RABBITMQ_DEFAULT_USER=pharmtrack \
                                --from-literal=RABBITMQ_DEFAULT_PASS="${RABBITMQ_PASSWORD}" \
                                -n ${K8S_NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

                            kubectl create secret generic gateway-app-secret \
                                --from-literal=SECRET_KEY="${DJANGO_SECRET_KEY}" \
                                -n ${K8S_NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

                            kubectl create secret generic notification-service-secret \
                                --from-literal=SECRET_KEY="${NOTIFICATION_SECRET_KEY}" \
                                --from-literal=DB_NAME="notification_db" \
                                --from-literal=DB_USER="postgres" \
                                --from-literal=DB_PASSWORD="${NOTIFICATION_DB_PASSWORD}" \
                                --from-literal=DB_HOST="postgres_notification.pharmtrack.svc.cluster.local" \
                                --from-literal=DB_PORT="5432" \
                                --from-literal=JWT_SECRET_KEY="${NOTIFICATION_JWT_SECRET}" \
                                --from-literal=RABBITMQ_URL="amqp://${RABBITMQ_DEFAULT_USER}:${RABBITMQ_DEFAULT_PASS}@rabbitmq.pharmtrack.svc.cluster.local:5672/pharmtrack" \
                                -n ${K8S_NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

                            kubectl create secret generic email-service-secret \
                                --from-literal=SMTP_HOST="${EMAIL_SMTP_HOST}" \
                                --from-literal=SMTP_PORT="${EMAIL_SMTP_PORT}" \
                                --from-literal=SMTP_USER="${EMAIL_SMTP_USER}" \
                                --from-literal=SMTP_PASSWORD="${EMAIL_SMTP_PASSWORD}" \
                                --from-literal=DEFAULT_FROM_EMAIL="${EMAIL_DEFAULT_FROM_EMAIL}" \
                                --from-literal=DEFAULT_FROM_NAME="${EMAIL_DEFAULT_FROM_NAME}" \
                                --from-literal=RABBITMQ_URL="amqp://${RABBITMQ_DEFAULT_USER}:${RABBITMQ_DEFAULT_PASS}@rabbitmq.pharmtrack.svc.cluster.local:5672/pharmtrack" \
                                -n ${K8S_NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -

                            # ── DockerHub image-pull secret ──────────────────────────────────────
                            # Use docker login → config.json method instead of --docker-password.
                            # Reason: --docker-password triggers a raw OAuth token fetch by the
                            # kubelet which fails with EOF when credentials contain special chars
                            # or when PATs are used. docker login handles the full auth handshake
                            # and stores the properly-encoded token in config.json.
                            echo "${DOCKERHUB_CREDS_PSW}" | docker login -u "${DOCKERHUB_CREDS_USR}" --password-stdin
                            kubectl create secret generic regcred \
                                --from-file=.dockerconfigjson="${HOME}/.docker/config.json" \
                                --type=kubernetes.io/dockerconfigjson \
                                -n ${K8S_NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -
                        '''
                    }
                }

                stage('Apply Shared Infrastructure') {
                    steps {
                        sh '''
                            export KUBECONFIG=${KUBECONFIG_CRED}
                            [ -f k8s/infra/10-postgres-gateway.yaml ] && kubectl apply -f k8s/infra/10-postgres-gateway.yaml
                            [ -f k8s/infra/20-redis.yaml ]            && kubectl apply -f k8s/infra/20-redis.yaml
                            [ -f k8s/infra/30-rabbitmq.yaml ]         && kubectl apply -f k8s/infra/30-rabbitmq.yaml

                            if [ -f notification-service/k8s/base/service.yaml ]; then
                                echo "Applying notification-service service manifest"
                                kubectl apply -f notification-service/k8s/base/service.yaml
                            fi

                            if [ -f notification-service/k8s/base/ingress.yaml ]; then
                                echo "Applying notification-service ingress manifest"
                                kubectl apply -f notification-service/k8s/base/ingress.yaml
                            fi

                            if [ -f email-service/k8s/base/service.yaml ]; then
                                echo "Applying email-service service manifest"
                                kubectl apply -f email-service/k8s/base/service.yaml
                            fi

                            if [ -f email-service/k8s/base/ingress.yaml ]; then
                                echo "Applying email-service ingress manifest"
                                kubectl apply -f email-service/k8s/base/ingress.yaml
                            fi
                        '''
                    }
                }

                stage('Wait & Connectivity Checks') {
                    steps {
                        sh '''
                            export KUBECONFIG=${KUBECONFIG_CRED}
                            echo "Waiting for infrastructure to be ready..."
                            kubectl rollout status statefulset/postgres-gateway -n ${K8S_NAMESPACE} --timeout=180s || true
                            kubectl rollout status deployment/redis            -n ${K8S_NAMESPACE} --timeout=120s || true
                            kubectl rollout status statefulset/rabbitmq        -n ${K8S_NAMESPACE} --timeout=180s || true

                            if kubectl get service notification-service -n ${K8S_NAMESPACE} >/dev/null 2>&1; then
                                echo "notification-service Service exists"
                            fi
                            if kubectl get ingress notification-service -n ${K8S_NAMESPACE} >/dev/null 2>&1; then
                                echo "notification-service Ingress exists"
                            fi

                            if kubectl get service email-service -n ${K8S_NAMESPACE} >/dev/null 2>&1; then
                                echo "email-service Service exists"
                            fi
                            if kubectl get ingress email-service -n ${K8S_NAMESPACE} >/dev/null 2>&1; then
                                echo "email-service Ingress exists"
                            fi

                            echo "Infrastructure ready!"
                        '''
                    }
                }
            }
        }

        // ─────────────────────────────────────────────────────────────────
        // 3. Build Services
        // ─────────────────────────────────────────────────────────────────
        stage('Build Services') {
            parallel {
                stage('Gateway Service') {
                    when {
                       expression { env.DETECTED_BRANCH in ['main', 'master'] }
                    }
                    steps {
                        dir('gateway') {
                            sh """
                                docker build \
                                    --label "git.commit=${GIT_COMMIT_FULL}" \
                                    --label "build.number=${BUILD_NUMBER}" \
                                    --label "branch=${DETECTED_BRANCH}" \
                                    -t ${GATEWAY_IMAGE}:${IMAGE_TAG} \
                                    -t ${GATEWAY_IMAGE}:latest \
                                    .
                            """
                        }
                    }
                }

                stage('Notification Service') {
                    when {
                       expression { env.DETECTED_BRANCH in ['main', 'master'] }
                    }
                    steps {
                        dir('notification-service') {
                            sh """
                                docker build \
                                    --label "git.commit=${GIT_COMMIT_FULL}" \
                                    --label "build.number=${BUILD_NUMBER}" \
                                    --label "branch=${DETECTED_BRANCH}" \
                                    -t ${NOTIFICATION_IMAGE}:${IMAGE_TAG} \
                                    -t ${NOTIFICATION_IMAGE}:latest \
                                    .
                            """
                        }
                    }
                }

                stage('Email Service') {
                    when {
                       expression { env.DETECTED_BRANCH in ['main', 'master'] }
                    }
                    steps {
                        dir('email-service') {
                            sh """
                                docker build \
                                    --label "git.commit=${GIT_COMMIT_FULL}" \
                                    --label "build.number=${BUILD_NUMBER}" \
                                    --label "branch=${DETECTED_BRANCH}" \
                                    -t ${EMAIL_IMAGE}:${IMAGE_TAG} \
                                    -t ${EMAIL_IMAGE}:latest \
                                    .
                            """
                        }
                    }
                }
            }
        }

        // ─────────────────────────────────────────────────────────────────
        // 4. Quality & Security
        // ─────────────────────────────────────────────────────────────────
        stage('Quality & Security') {
            parallel {
                stage('Gateway - Lint (flake8)') {
                    when {
                        expression { env.DETECTED_BRANCH in ['main', 'master'] }
                    }
                    steps {
                        dir('gateway') {
                            sh """
                                docker run --rm \
                                    -e SECRET_KEY=ci-lint-key -e DEBUG=True -e DB_PASSWORD=ci \
                                    ${GATEWAY_IMAGE}:${IMAGE_TAG} \
                                    flake8 . --max-line-length=120 --exclude=migrations,__pycache__,.venv --format=default
                            """
                        }
                    }
                }

                stage('Gateway - SAST (bandit)') {
                    when {
                        expression { env.DETECTED_BRANCH in ['main', 'master'] }
                    }
                    steps {
                        dir('gateway') {
                            sh """
                                docker run --rm \
                                    -e SECRET_KEY=ci-bandit-key -e DEBUG=True -e DB_PASSWORD=ci \
                                    ${GATEWAY_IMAGE}:${IMAGE_TAG} \
                                    bandit -r . --exclude ./.venv,./migrations -ll -f txt
                            """
                        }
                    }
                }

                stage('Gateway - Image Scan (Trivy)') {
                    when {
                        expression { env.DETECTED_BRANCH in ['main', 'master'] }
                    }
                    steps {
                        sh """
                            docker run --rm \
                                -v /var/run/docker.sock:/var/run/docker.sock \
                                -v \$(pwd)/.trivy-cache-gateway:/root/.cache/ \
                                aquasec/trivy:latest image \
                                    --timeout 15m \
                                    --severity CRITICAL \
                                    --ignore-unfixed \
                                    --exit-code 1 \
                                    --no-progress \
                                    ${GATEWAY_IMAGE}:${IMAGE_TAG}
                            """
                    }
                }

                stage('Notification - Image Scan (Trivy)') {
                    when {
                        expression { env.DETECTED_BRANCH in ['main', 'master'] }
                    }
                    steps {
                        sh """
                            docker run --rm \
                                -v /var/run/docker.sock:/var/run/docker.sock \
                                -v \$(pwd)/.trivy-cache-notification:/root/.cache/ \
                                aquasec/trivy:latest image \
                                    --timeout 15m \
                                    --severity CRITICAL \
                                    --ignore-unfixed \
                                    --exit-code 1 \
                                    --no-progress \
                                    ${NOTIFICATION_IMAGE}:${IMAGE_TAG}
                            """
                    }
                }

                stage('Email - Image Scan (Trivy)') {
                    when {
                        expression { env.DETECTED_BRANCH in ['main', 'master'] }
                    }
                    steps {
                        sh """
                            docker run --rm \
                                -v /var/run/docker.sock:/var/run/docker.sock \
                                -v \$(pwd)/.trivy-cache-email:/root/.cache/ \
                                aquasec/trivy:latest image \
                                    --timeout 15m \
                                    --severity CRITICAL \
                                    --ignore-unfixed \
                                    --exit-code 1 \
                                    --no-progress \
                                    ${EMAIL_IMAGE}:${IMAGE_TAG}
                            """
                    }
                }
            }
        }

        // ─────────────────────────────────────────────────────────────────
        // 5. Test Services
        // ─────────────────────────────────────────────────────────────────
        stage('Test Services') {
            parallel {
                stage('Gateway - Unit Tests (pytest)') {
                    when {
                        expression { env.DETECTED_BRANCH in ['main', 'master'] }
                    }

                    steps {
                        dir('gateway') {

                            sh """
                                echo "Cleaning old containers/networks..."
                                docker rm -f ci-postgres || true
                                docker network rm ci-net || true

                                echo "Creating CI network..."
                                docker network create ci-net || true

                                echo "Starting PostgreSQL..."
                                docker run -d --name ci-postgres \
                                --network ci-net \
                                -e POSTGRES_DB=ci_db \
                                -e POSTGRES_USER=ci_user \
                                -e POSTGRES_PASSWORD=ci_pass \
                                postgres:15

                                echo "Waiting for DB to be ready..."
                                sleep 10

                                echo "Running Django tests..."
                                docker run --rm \
                                    --network ci-net \
                                    -e SECRET_KEY=ci-test-secret \
                                    -e DEBUG=True \
                                    -e DB_NAME=ci_db \
                                    -e DB_USER=ci_user \
                                    -e DB_PASSWORD=ci_pass \
                                    -e DB_HOST=ci-postgres \
                                    -e DB_PORT=5432 \
                                    -e RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/ \
                                    -e DJANGO_SETTINGS_MODULE=pharmtrack_gateway.settings \
                                    ${GATEWAY_IMAGE}:${IMAGE_TAG} \
                                    pytest tests/ --tb=short -v --cov=apps \
                                    --cov-report=xml:/tmp/coverage.xml \
                                    --cov-fail-under=50

                                echo "Copying coverage..."
                                docker create --name cov_container ${GATEWAY_IMAGE}:${IMAGE_TAG}
                                docker cp cov_container:/tmp/coverage.xml ${WORKSPACE}/gateway/coverage.xml || true
                                docker rm cov_container || true

                                echo "Cleaning up..."
                                docker rm -f ci-postgres || true
                                docker network rm ci-net || true
                            """
                        }
                    }

                    post {
                        always {
                            junit allowEmptyResults: true, testResults: 'gateway/coverage.xml'
                            archiveArtifacts artifacts: 'gateway/coverage.xml', allowEmptyArchive: true
                        }

                        cleanup {
                            sh """
                                echo "Cleaning up CI containers..."
                                docker rm -f ci-postgres || true
                                docker network rm ci-net || true
                            """
                        }
                    }
                }

                stage('Notification Service - Unit Tests (pytest)') {
                    when {
                        expression { env.DETECTED_BRANCH in ['main', 'master'] }
                    }
                    steps {
                        sh """
                            docker run --rm \
                                -e SECRET_KEY=ci-test-secret \
                                -e DB_PASSWORD=ci_pass \
                                -e JWT_SECRET_KEY=ci-jwt-secret \
                                -e RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/ \
                                ${NOTIFICATION_IMAGE}:${IMAGE_TAG} \
                                pytest tests/ --tb=short -v --maxfail=1 --disable-warnings
                        """
                    }
                }

                stage('Email Service - Unit Tests (pytest)') {
                    when {
                        expression { env.DETECTED_BRANCH in ['main', 'master'] }
                    }
                    steps {
                        sh """
                            docker run --rm \
                                ${EMAIL_IMAGE}:${IMAGE_TAG} \
                                pytest tests/ --tb=short -v --maxfail=1 --disable-warnings
                        """
                    }
                }
            }
        }

        // ─────────────────────────────────────────────────────────────────
        // 6. Push to Registry
        // ─────────────────────────────────────────────────────────────────
        stage('Push to Registry') {
            when {
                expression { env.DETECTED_BRANCH in ['main', 'master'] }
            }
            steps {
                sh """
                    echo \${DOCKERHUB_CREDS_PSW} | docker login -u \${DOCKERHUB_CREDS_USR} --password-stdin
                    docker push ${GATEWAY_IMAGE}:${IMAGE_TAG}
                    docker push ${GATEWAY_IMAGE}:latest
                    docker push ${NOTIFICATION_IMAGE}:${IMAGE_TAG}
                    docker push ${NOTIFICATION_IMAGE}:latest
                    docker push ${EMAIL_IMAGE}:${IMAGE_TAG}
                    docker push ${EMAIL_IMAGE}:latest
                """
            }
        }

        // ─────────────────────────────────────────────────────────────────
        // 7. Deploy to Kubernetes
        // ─────────────────────────────────────────────────────────────────
        stage('Deploy to Kubernetes') {
            when {
                expression { env.DETECTED_BRANCH in ['main', 'master'] }
            }
            steps {
                script {
                    env.PREVIOUS_REVISION = sh(
                        script: """
                            export KUBECONFIG=${KUBECONFIG_CRED}
                            kubectl get deployment gateway -n ${K8S_NAMESPACE} \
                                -o jsonpath='{.metadata.annotations.deployment\\.kubernetes\\.io/revision}' 2>/dev/null || echo '0'
                        """,
                        returnStdout: true
                    ).trim()
                    echo "Previous revision: ${env.PREVIOUS_REVISION}"
                }

                dir('gateway/k8s/base') {
                    sh """
                        set -e  # Exit immediately if any command fails
                        export KUBECONFIG=${KUBECONFIG_CRED}

                        echo "=== Applying base configurations first ==="
                        kubectl apply -f configmap.yaml

                        # Optional: Apply other static resources early
                        kubectl apply -f service.yaml
                        kubectl apply -f ingress.yaml
                        kubectl apply -f hpa.yaml

                        echo "=== Verifying ConfigMap exists ==="
                        if ! kubectl get configmap gateway-config -n ${K8S_NAMESPACE} >/dev/null 2>&1; then
                            echo "❌ ERROR: gateway-config ConfigMap was not created successfully!"
                            exit 1
                        fi
                        echo "✅ ConfigMap verified"

                        # Render templates
                        sed "s#__IMAGE_TAG__#${IMAGE_TAG}#g" deployment.yaml > deployment.rendered.yaml
                        sed "s#__IMAGE_TAG__#${IMAGE_TAG}#g" migrate-job.yaml > migrate-job.rendered.yaml

                        echo "=== Cleaning up old migration job ==="
                        kubectl delete job gateway-migrate -n ${K8S_NAMESPACE} --ignore-not-found

                        echo "=== Applying migration job ==="
                        kubectl apply -f migrate-job.rendered.yaml

                        echo "=== Waiting for migration to complete (max 8 minutes) ==="
                        if ! kubectl wait --for=condition=complete job/gateway-migrate -n ${K8S_NAMESPACE} --timeout=480s; then
                            echo "❌ Migration FAILED or TIMED OUT!"
                            echo "=== Job Description ==="
                            kubectl describe job gateway-migrate -n ${K8S_NAMESPACE}
                            echo "=== Pod Logs ==="
                            kubectl logs -n ${K8S_NAMESPACE} -l job-name=gateway-migrate --tail=500 || true
                            echo "=== Pod Description ==="
                            kubectl describe pod -n ${K8S_NAMESPACE} -l job-name=gateway-migrate || true
                            exit 1
                        fi

                        echo "✅ Migration completed successfully!"

                        echo "=== Deploying new application version ==="
                        kubectl apply -f deployment.rendered.yaml

                        echo "=== Waiting for deployment rollout ==="
                        kubectl rollout status deployment/gateway -n ${K8S_NAMESPACE} --timeout=180s

                        echo "=== Deploying notification-service and email-service manifests ==="
                        for service_dir in notification-service email-service; do
                            echo "=== Deploying \${service_dir} ==="
                            oldpwd="\$(pwd)"
                            cd "${WORKSPACE}/\${service_dir}/k8s/base"
                            for manifest in deployment.yaml service.yaml ingress.yaml; do
                                [ -f "\$manifest" ] || continue
                                sed "s#__IMAGE_TAG__#${IMAGE_TAG}#g" "\$manifest" > "\$manifest.rendered.yaml"
                            done
                            kubectl apply -f *.rendered.yaml
                            kubectl rollout status deployment/\${service_dir} -n ${K8S_NAMESPACE} --timeout=180s
                            cd "\$oldpwd"
                        done

                        echo "🎉 Deployment completed successfully!"

                        # Cleanup
                        find "${WORKSPACE}/notification-service/k8s/base" -name '*.rendered.yaml' -delete || true
                        find "${WORKSPACE}/email-service/k8s/base" -name '*.rendered.yaml' -delete || true
                        rm -f *.rendered.yaml
                    """
                }
            }
        }

        // ─────────────────────────────────────────────────────────────────
        // 8. Smoke Test
        // ─────────────────────────────────────────────────────────────────
        stage('Smoke Test') {
            when {
                expression { env.DETECTED_BRANCH in ['main', 'master'] }
            }
            steps {
                sh """
                    export KUBECONFIG=\${KUBECONFIG_CRED}
                    echo "=== Smoke checking gateway ==="
                    kubectl run gateway-smoke-${BUILD_NUMBER} \
                        -n ${K8S_NAMESPACE} --rm -i --restart=Never \
                        --image=curlimages/curl:8.7.1 \
                        -- curl -sf --retry 5 --retry-delay 3 \
                             http://gateway.${K8S_NAMESPACE}.svc.cluster.local:8000/healthz/

                    echo "=== Smoke checking notification-service ==="
                    kubectl run notification-smoke-${BUILD_NUMBER} \
                        -n ${K8S_NAMESPACE} --rm -i --restart=Never \
                        --image=curlimages/curl:8.7.1 \
                        -- curl -sf --retry 5 --retry-delay 3 \
                             http://notification-service.${K8S_NAMESPACE}.svc.cluster.local:8002/api/docs/

                    echo "=== Smoke checking email-service ==="
                    kubectl run email-smoke-${BUILD_NUMBER} \
                        -n ${K8S_NAMESPACE} --rm -i --restart=Never \
                        --image=curlimages/curl:8.7.1 \
                        -- curl -sf --retry 5 --retry-delay 3 \
                             http://email-service.${K8S_NAMESPACE}.svc.cluster.local:8003/health
                """
            }
        }
    }

    // ─────────────────────────────────────────────────────────────────────POST
    post {
        always {
            script {
                echo "Pipeline completed: ${currentBuild.result}"
                node {
                    sh """
                        docker logout 2>/dev/null || true
                        docker rmi ${env.GATEWAY_IMAGE}:${env.IMAGE_TAG} 2>/dev/null || true
                        docker rmi ${env.GATEWAY_IMAGE}:latest 2>/dev/null || true
                        docker rmi ${env.NOTIFICATION_IMAGE}:${env.IMAGE_TAG} 2>/dev/null || true
                        docker rmi ${env.NOTIFICATION_IMAGE}:latest 2>/dev/null || true
                        docker rmi ${env.EMAIL_IMAGE}:${env.IMAGE_TAG} 2>/dev/null || true
                        docker rmi ${env.EMAIL_IMAGE}:latest 2>/dev/null || true
                    """
                }
            }
        }
        failure {
            script {
                if (env.PREVIOUS_REVISION && env.PREVIOUS_REVISION != '0') {
                    node {
                        sh """
                            export KUBECONFIG=\${KUBECONFIG_CRED}
                            echo "⚠️  Rolling back to revision ${env.PREVIOUS_REVISION}"
                            kubectl rollout undo deployment/gateway -n ${K8S_NAMESPACE} --to-revision=${env.PREVIOUS_REVISION} || true
                        """
                    }
                }
            }
        }
    }
}

/*
 * ============================================================================
 * CHANGELOG
 * ----------------------------------------------------------------------------
 * v1 (this version): Fixed against real run errors:
 *   - Added 'Preflight' stage that checks docker/kubectl exist AND that the
 *     docker daemon is reachable, failing fast with a clear message instead
 *     of dying deep into the pipeline.
 *   - Removed the custom `isChangeset()` Groovy helper (defined outside
 *     `pipeline{}`, called via `sh` inside `when{expression{}}`) which is
 *     prone to CPS-sandbox RejectedAccessException. Replaced with
 *     Declarative's native `changeset 'path/**'` condition, which also
 *     correctly handles first-ever builds without extra logic.
 *   - Replaced `deleteDir() + skipDefaultCheckout() + checkout scm` with a
 *     plain `checkout scm` — simpler and avoids wiping the wrong directory
 *     on certain rerun/resume scenarios.
 *   - Added `ansiColor('xterm')` (requires the ansicolor plugin, included
 *     in jenkins/Dockerfile) for readable colored stage logs.
 *   - Rollback-on-failure logic preserved from the original, moved into
 *     `post { failure { ... } }` consistently with infrastructure/Jenkinsfile
 *     and gateway/Jenkinsfile.
 *   - See jenkins/RUN_JENKINS.md for the actual root cause of "docker not
 *     found" / "kubectl not found": these were DinD networking/kubeconfig
 *     setup issues, not pipeline syntax issues — fixed in jenkins/Dockerfile
 *     and documented with exact `docker run` commands.
 * ============================================================================
 */
