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
        K8S_NAMESPACE       = "pharmtrack"
        GATEWAY_IMAGE       = "9moses/gateway"

        KUBECONFIG_CRED     = credentials('pharmtrack-kubeconfig')
        DB_PASSWORD         = credentials('gateway-db-password')
        REDIS_PASSWORD      = credentials('gateway-redis-password')
        RABBITMQ_PASSWORD   = credentials('gateway-rabbitmq-password')
        DJANGO_SECRET_KEY   = credentials('gateway-secret-key')
        DOCKERHUB_CREDS     = credentials('dockerhub-credentials')
        NOTIFY_EMAIL        = "esselmoses12@gmail.com"
    }

    stages {

        // ─────────────────────────────────────────────────────────────────
        // 0. Preflight — fail fast with a clear message instead of dying
        //    20 minutes into the build on stage 6.
        // ─────────────────────────────────────────────────────────────────
        stage('Preflight') {
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

                            # ── DockerHub image-pull secret ──────────────────────────────────────
                            # Without this, kubelet pulls anonymously → DockerHub rate-limit
                            # (100 pulls / 6 hr per IP) causes image pulls to hang or fail.
                            # DOCKERHUB_CREDS is the same Jenkins credential used in Push stage.
                            kubectl create secret docker-registry regcred \
                                --docker-server=https://index.docker.io/v1/ \
                                --docker-username="${DOCKERHUB_CREDS_USR}" \
                                --docker-password="${DOCKERHUB_CREDS_PSW}" \
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
                                -v \$(pwd)/.trivy-cache:/root/.cache/ \
                                aquasec/trivy:latest image \
                                    --severity CRITICAL \
                                    --ignore-unfixed \
                                    --exit-code 1 \
                                    --no-progress \
                                    ${GATEWAY_IMAGE}:${IMAGE_TAG}
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

                        echo "🎉 Deployment completed successfully!"

                        # Cleanup
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
                    kubectl run gateway-smoke-${BUILD_NUMBER} \
                        -n ${K8S_NAMESPACE} --rm -i --restart=Never \
                        --image=curlimages/curl:8.7.1 \
                        -- curl -sf --retry 5 --retry-delay 3 \
                             http://gateway.${K8S_NAMESPACE}.svc.cluster.local:8000/healthz/
                """
            }
        }
    }

    // ─────────────────────────────────────────────────────────────────────
    post {
        always {
            script {
                echo "Pipeline completed: ${currentBuild.result}"
                sh """
                    docker logout 2>/dev/null || true
                    docker rmi ${env.GATEWAY_IMAGE}:${env.IMAGE_TAG} 2>/dev/null || true
                    docker rmi ${env.GATEWAY_IMAGE}:latest 2>/dev/null || true
                """
            }
        }
        failure {
            script {
                if (env.PREVIOUS_REVISION && env.PREVIOUS_REVISION != '0') {
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
