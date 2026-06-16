pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '15'))
        timeout(time: 45, unit: 'MINUTES')
        skipDefaultCheckout()  // We handle checkout explicitly
    }

    environment {
        // --- Shared Environment Variables ---
        IMAGE_TAG           = "${GIT_COMMIT[0..7]}-${BUILD_NUMBER}"
        K8S_NAMESPACE       = "pharmtrack"

        // --- Gateway Service Specific ---
        GATEWAY_IMAGE       = "pharmtrack/gateway"
        
        // --- Credentials ---
        KUBECONFIG_CRED     = credentials('pharmtrack-kubeconfig')
        DB_PASSWORD         = credentials('gateway-db-password')
        REDIS_PASSWORD      = credentials('gateway-redis-password')
        RABBITMQ_PASSWORD   = credentials('gateway-rabbitmq-password')
        DJANGO_SECRET_KEY   = credentials('gateway-secret-key')
        DOCKERHUB_CREDS     = credentials('dockerhub-credentials')
        NOTIFY_EMAIL        = credentials('notify-email')
    }

    stages {
        // ==========================================
        // STAGE 1: Checkout & Branch Detection
        // ==========================================
        stage('Checkout') {
            steps {
                checkout scm
                script {
                    // Detect branch name properly
                    if (env.BRANCH_NAME) {
                        env.DETECTED_BRANCH = env.BRANCH_NAME
                    } else if (env.GIT_BRANCH) {
                        env.DETECTED_BRANCH = env.GIT_BRANCH.replace('origin/', '')
                    } else {
                        env.DETECTED_BRANCH = sh(
                            script: 'git rev-parse --abbrev-ref HEAD',
                            returnStdout: true
                        ).trim()
                    }
                    
                    // Get commit hash
                    env.GIT_COMMIT_FULL = sh(
                        script: 'git rev-parse HEAD',
                        returnStdout: true
                    ).trim()
                    
                    env.GIT_COMMIT_SHORT = env.GIT_COMMIT_FULL[0..7]
                    env.IMAGE_TAG = "${env.GIT_COMMIT_SHORT}-${env.BUILD_NUMBER}"
                    
                    echo "========================================="
                    echo "Branch: ${env.DETECTED_BRANCH}"
                    echo "Commit: ${env.GIT_COMMIT_FULL}"
                    echo "Image Tag: ${env.IMAGE_TAG}"
                    echo "========================================="
                    
                    // Set build display name
                    currentBuild.displayName = "#${env.BUILD_NUMBER} - ${env.DETECTED_BRANCH} (${env.GIT_COMMIT_SHORT})"
                }
            }
        }

        // ==========================================
        // STAGE 2: Infrastructure Provisioning
        // ==========================================
        stage('Infrastructure') {
            when {
                expression {
                    // Run on main/master or when infra files change
                    env.DETECTED_BRANCH == 'main' || 
                    env.DETECTED_BRANCH == 'master' ||
                    isChangeset('k8s/infra/')
                }
            }
            stages {
                stage('Validate Manifests') {
                    steps {
                        script {
                            sh '''
                                export KUBECONFIG=${KUBECONFIG_CRED}
                                
                                for f in k8s/infra/*.yaml; do
                                    if [ -f "$f" ]; then
                                        case "$f" in
                                            *secrets.example*) 
                                                echo "Skipping $f (template only)"
                                                continue 
                                                ;;
                                        esac
                                        echo "Validating $f ..."
                                        kubectl apply --dry-run=client -f "$f"
                                    fi
                                done
                            '''
                        }
                    }
                }
                
                stage('Inject Shared Secrets') {
                    steps {
                        script {
                            sh '''
                                export KUBECONFIG=${KUBECONFIG_CRED}
                                
                                # Create namespace if not exists
                                kubectl create namespace ${K8S_NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -
                                
                                # Create or update secrets
                                kubectl create secret generic gateway-db-secret \
                                    --from-literal=POSTGRES_USER=postgres \
                                    --from-literal=POSTGRES_PASSWORD="${DB_PASSWORD}" \
                                    -n ${K8S_NAMESPACE} \
                                    --dry-run=client -o yaml | kubectl apply -f -
                                
                                kubectl create secret generic redis-secret \
                                    --from-literal=REDIS_PASSWORD="${REDIS_PASSWORD}" \
                                    -n ${K8S_NAMESPACE} \
                                    --dry-run=client -o yaml | kubectl apply -f -
                                
                                kubectl create secret generic rabbitmq-secret \
                                    --from-literal=RABBITMQ_DEFAULT_USER=pharmtrack \
                                    --from-literal=RABBITMQ_DEFAULT_PASS="${RABBITMQ_PASSWORD}" \
                                    -n ${K8S_NAMESPACE} \
                                    --dry-run=client -o yaml | kubectl apply -f -
                                
                                kubectl create secret generic gateway-app-secret \
                                    --from-literal=SECRET_KEY="${DJANGO_SECRET_KEY}" \
                                    -n ${K8S_NAMESPACE} \
                                    --dry-run=client -o yaml | kubectl apply -f -
                            '''
                        }
                    }
                }
                
                stage('Apply Shared Infrastructure') {
                    steps {
                        script {
                            sh '''
                                export KUBECONFIG=${KUBECONFIG_CRED}
                                
                                [ -f k8s/infra/10-postgres-gateway.yaml ] && kubectl apply -f k8s/infra/10-postgres-gateway.yaml
                                [ -f k8s/infra/20-redis.yaml ] && kubectl apply -f k8s/infra/20-redis.yaml
                                [ -f k8s/infra/30-rabbitmq.yaml ] && kubectl apply -f k8s/infra/30-rabbitmq.yaml
                            '''
                        }
                    }
                }
                
                stage('Wait & Connectivity Checks') {
                    steps {
                        script {
                            sh '''
                                export KUBECONFIG=${KUBECONFIG_CRED}
                                
                                echo "Waiting for infrastructure to be ready..."
                                kubectl rollout status statefulset/postgres-gateway -n ${K8S_NAMESPACE} --timeout=180s || true
                                kubectl rollout status deployment/redis -n ${K8S_NAMESPACE} --timeout=120s || true
                                kubectl rollout status statefulset/rabbitmq -n ${K8S_NAMESPACE} --timeout=180s || true
                                
                                echo "Infrastructure ready!"
                            '''
                        }
                    }
                }
            }
        }

        // ==========================================
        // STAGE 3: Build Services
        // ==========================================
        stage('Build Services') {
            parallel {
                stage('Gateway Service') {
                    when {
                        expression {
                            env.DETECTED_BRANCH == 'main' || 
                            env.DETECTED_BRANCH == 'master' ||
                            isChangeset('gateway/')
                        }
                    }
                    steps {
                        script {
                            sh """
                                echo "Building Gateway image..."
                                cd gateway
                                docker build \
                                    --label "git.commit=${GIT_COMMIT_FULL}" \
                                    --label "build.number=${BUILD_NUMBER}" \
                                    --label "branch=${DETECTED_BRANCH}" \
                                    -t ${GATEWAY_IMAGE}:${IMAGE_TAG} \
                                    -t ${GATEWAY_IMAGE}:latest \
                                    .
                                echo "Build complete: ${GATEWAY_IMAGE}:${IMAGE_TAG}"
                            """
                        }
                    }
                }
            }
        }

        // ==========================================
        // STAGE 4: Quality & Security
        // ==========================================
        stage('Quality & Security') {
            parallel {
                stage('Gateway - Lint (flake8)') {
                    when {
                        expression {
                            env.DETECTED_BRANCH == 'main' || 
                            env.DETECTED_BRANCH == 'master' ||
                            isChangeset('gateway/')
                        }
                    }
                    steps {
                        script {
                            dir('gateway') {
                                sh """
                                    docker run --rm \
                                        -e SECRET_KEY=ci-lint-key \
                                        -e DEBUG=True \
                                        -e DB_PASSWORD=ci \
                                        ${GATEWAY_IMAGE}:${IMAGE_TAG} \
                                        flake8 . \
                                            --max-line-length=120 \
                                            --exclude=migrations,__pycache__,.venv \
                                            --format=default
                                """
                            }
                        }
                    }
                }

                stage('Gateway - SAST (bandit)') {
                    when {
                        expression {
                            env.DETECTED_BRANCH == 'main' || 
                            env.DETECTED_BRANCH == 'master' ||
                            isChangeset('gateway/')
                        }
                    }
                    steps {
                        script {
                            dir('gateway') {
                                sh """
                                    docker run --rm \
                                        -e SECRET_KEY=ci-bandit-key \
                                        -e DEBUG=True \
                                        -e DB_PASSWORD=ci \
                                        ${GATEWAY_IMAGE}:${IMAGE_TAG} \
                                        bandit -r . \
                                            --exclude ./.venv,./migrations \
                                            -ll \
                                            -f txt
                                """
                            }
                        }
                    }
                }

                stage('Gateway - Image Scan (Trivy)') {
                    when {
                        expression {
                            env.DETECTED_BRANCH == 'main' || 
                            env.DETECTED_BRANCH == 'master' ||
                            isChangeset('gateway/')
                        }
                    }
                    steps {
                        script {
                            sh """
                                echo "Running Trivy scan on ${GATEWAY_IMAGE}:${IMAGE_TAG}"
                                docker run --rm \
                                    -v /var/run/docker.sock:/var/run/docker.sock \
                                    -v \$(pwd)/.trivy-cache:/root/.cache/ \
                                    aquasec/trivy:latest image \
                                        --severity HIGH,CRITICAL \
                                        --no-progress \
                                        ${GATEWAY_IMAGE}:${IMAGE_TAG}
                            """
                        }
                    }
                }
            }
        }

        // ==========================================
        // STAGE 5: Test Services
        // ==========================================
        stage('Test Services') {
            parallel {
                stage('Gateway - Unit Tests (pytest)') {
                    when {
                        expression {
                            env.DETECTED_BRANCH == 'main' || 
                            env.DETECTED_BRANCH == 'master' ||
                            isChangeset('gateway/')
                        }
                    }
                    steps {
                        script {
                            dir('gateway') {
                                sh """
                                    docker run --rm \
                                        -e SECRET_KEY=ci-test-secret \
                                        -e DEBUG=True \
                                        -e DB_PASSWORD=ci \
                                        -e DJANGO_SETTINGS_MODULE=pharmtrack_gateway.settings \
                                        -v \$(pwd)/coverage.xml:/app/coverage.xml \
                                        ${GATEWAY_IMAGE}:${IMAGE_TAG} \
                                        pytest tests/ \
                                            --tb=short -v \
                                            --cov=. \
                                            --cov-report=xml:/app/coverage.xml \
                                            --cov-fail-under=70
                                """
                            }
                        }
                    }
                    post {
                        always {
                            junit allowEmptyResults: true, testResults: 'gateway/coverage.xml'
                        }
                    }
                }
            }
        }

        // ==========================================
        // STAGE 6: Push to Registry
        // ==========================================
        stage('Push to Registry') {
            when {
                expression {
                    env.DETECTED_BRANCH == 'main' || env.DETECTED_BRANCH == 'master'
                }
            }
            steps {
                script {
                    sh """
                        echo "Pushing images to registry..."
                        echo \${DOCKERHUB_CREDS_PSW} | docker login -u \${DOCKERHUB_CREDS_USR} --password-stdin
                        docker push ${GATEWAY_IMAGE}:${IMAGE_TAG}
                        docker push ${GATEWAY_IMAGE}:latest
                        echo "Push complete!"
                    """
                }
            }
        }

        // ==========================================
        // STAGE 7: Deploy to Kubernetes
        // ==========================================
        stage('Deploy to Kubernetes') {
            when {
                expression {
                    env.DETECTED_BRANCH == 'main' || env.DETECTED_BRANCH == 'master'
                }
            }
            steps {
                script {
                    // Save previous revision for rollback
                    env.PREVIOUS_REVISION = sh(
                        script: """
                            export KUBECONFIG=\${KUBECONFIG_CRED}
                            kubectl get deployment gateway -n ${K8S_NAMESPACE} \
                                -o jsonpath='{.metadata.annotations.deployment\\.kubernetes\\.io/revision}' 2>/dev/null || echo '0'
                        """,
                        returnStdout: true
                    ).trim()
                    
                    echo "Previous revision: ${env.PREVIOUS_REVISION}"
                }
                
                dir('gateway/k8s/base') {
                    sh """
                        export KUBECONFIG=\${KUBECONFIG_CRED}
                        
                        # Render deployment with correct image tag
                        sed 's#__IMAGE_TAG__#${IMAGE_TAG}#g' deployment.yaml > deployment.rendered.yaml
                        sed 's#__IMAGE_TAG__#${IMAGE_TAG}#g' migrate-job.yaml > migrate-job.rendered.yaml
                        
                        # Run migrations
                        echo "Running database migrations..."
                        kubectl delete job gateway-migrate -n ${K8S_NAMESPACE} --ignore-not-found
                        kubectl apply -f migrate-job.rendered.yaml
                        kubectl wait --for=condition=complete job/gateway-migrate -n ${K8S_NAMESPACE} --timeout=120s
                        
                        # Apply configuration
                        echo "Deploying application..."
                        kubectl apply -f configmap.yaml
                        kubectl apply -f service.yaml
                        kubectl apply -f ingress.yaml
                        kubectl apply -f hpa.yaml
                        kubectl apply -f deployment.rendered.yaml
                        
                        # Wait for rollout
                        kubectl rollout status deployment/gateway -n ${K8S_NAMESPACE} --timeout=180s
                        
                        # Cleanup
                        rm -f deployment.rendered.yaml migrate-job.rendered.yaml
                        
                        echo "Deployment complete!"
                    """
                }
            }
        }

        // ==========================================
        // STAGE 8: Smoke Test
        // ==========================================
        stage('Smoke Test') {
            when {
                expression {
                    env.DETECTED_BRANCH == 'main' || env.DETECTED_BRANCH == 'master'
                }
            }
            steps {
                script {
                    sh """
                        export KUBECONFIG=\${KUBECONFIG_CRED}
                        
                        echo "Running smoke tests..."
                        kubectl run gateway-smoke-${BUILD_NUMBER} \
                            -n ${K8S_NAMESPACE} \
                            --rm -i \
                            --restart=Never \
                            --image=curlimages/curl:8.7.1 \
                            -- curl -sf --retry 5 --retry-delay 3 \
                                 http://gateway.${K8S_NAMESPACE}.svc.cluster.local:8000/healthz/
                        
                        echo "Smoke test passed!"
                    """
                }
            }
        }
    }

    // ==========================================
    // POST ACTIONS
    // ==========================================
    post {
        always {
            script {
                echo "========================================="
                echo "Pipeline completed: ${currentBuild.result}"
                echo "========================================="
                
                // Cleanup Docker
                sh """
                    docker logout 2>/dev/null || true
                    docker rmi ${GATEWAY_IMAGE}:${IMAGE_TAG} 2>/dev/null || true
                    docker rmi ${GATEWAY_IMAGE}:latest 2>/dev/null || true
                """
            }
        }
        
        failure {
            script {
                // Trigger rollback if deployment failed
                if (env.PREVIOUS_REVISION && env.PREVIOUS_REVISION != '0') {
                    sh """
                        export KUBECONFIG=\${KUBECONFIG_CRED}
                        echo "⚠️  Deploy failed — rolling back to revision ${PREVIOUS_REVISION}"
                        kubectl rollout undo deployment/gateway -n ${K8S_NAMESPACE} --to-revision=${PREVIOUS_REVISION} || true
                        kubectl rollout status deployment/gateway -n ${K8S_NAMESPACE} --timeout=120s || true
                    """
                }
            }
            
            // Send failure notification
            emailext(
                subject: "❌ Pipeline FAILED: ${env.JOB_NAME} - Build #${env.BUILD_NUMBER}",
                body: """
                    Pipeline failed!
                    
                    Job: ${env.JOB_NAME}
                    Build: #${env.BUILD_NUMBER}
                    Branch: ${env.DETECTED_BRANCH}
                    Commit: ${env.GIT_COMMIT_SHORT}
                    
                    View details: ${env.BUILD_URL}
                """,
                to: "${NOTIFY_EMAIL}",
                mimeType: 'text/plain'
            )
        }
        
        success {
            emailext(
                subject: "✅ Pipeline SUCCESS: ${env.JOB_NAME} - Build #${env.BUILD_NUMBER}",
                body: """
                    Pipeline completed successfully!
                    
                    Job: ${env.JOB_NAME}
                    Build: #${env.BUILD_NUMBER}
                    Branch: ${env.DETECTED_BRANCH}
                    Commit: ${env.GIT_COMMIT_SHORT}
                    Image: ${GATEWAY_IMAGE}:${IMAGE_TAG}
                    
                    View details: ${env.BUILD_URL}
                """,
                to: "${NOTIFY_EMAIL}",
                mimeType: 'text/plain'
            )
        }
    }
}

// Helper function to check for changes in directory
def isChangeset(String path) {
    if (!env.GIT_PREVIOUS_COMMIT && !env.GIT_PREVIOUS_SUCCESSFUL_COMMIT) {
        return true  // First build, assume changes
    }
    
    def previousCommit = env.GIT_PREVIOUS_COMMIT ?: env.GIT_PREVIOUS_SUCCESSFUL_COMMIT
    if (!previousCommit) {
        return true
    }
    
    def changes = sh(
        script: "git diff --name-only ${previousCommit}..HEAD -- ${path}",
        returnStdout: true
    ).trim()
    
    return !changes.isEmpty()
}