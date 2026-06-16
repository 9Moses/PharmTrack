pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '15'))
        timeout(time: 45, unit: 'MINUTES')
    }

    environment {
        // --- Shared Environment Variables ---
        IMAGE_TAG           = "${env.GIT_COMMIT[0..7]}-${env.BUILD_NUMBER}"
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
        // STAGE 1: Checkout
        // ==========================================
        stage('Checkout') {
            steps {
                checkout scm
                echo "Building branch: ${env.BRANCH_NAME} | commit: ${env.GIT_COMMIT[0..7]}"
            }
        }

        // ==========================================
        // STAGE 2: Infrastructure Provisioning
        // ==========================================
        stage('Infrastructure') {
            when {
                anyOf { changeset "k8s/infra/**"; branch 'main'; branch 'master' }
            }
            stages {
                stage('Validate Manifests') {
                    steps {
                        sh """
                            export KUBECONFIG=\$KUBECONFIG_CRED
                            for f in k8s/infra/*.yaml; do
                                case "\$f" in
                                    *secrets.example*) echo "Skipping \$f (template only)"; continue ;;
                                esac
                                echo "Validating \$f ..."
                                kubectl apply --dry-run=client -f "\$f"
                            done
                        """
                    }
                }
                stage('Inject Shared Secrets') {
                    steps {
                        sh """
                            export KUBECONFIG=\$KUBECONFIG_CRED
                            kubectl apply -f k8s/infra/00-namespace.yaml || true

                            kubectl create secret generic gateway-db-secret \\
                                --from-literal=POSTGRES_USER=postgres \\
                                --from-literal=POSTGRES_PASSWORD="\$DB_PASSWORD" \\
                                -n ${K8S_NAMESPACE} \\
                                --save-config --dry-run=client -o yaml | kubectl apply -f -

                            kubectl create secret generic redis-secret \\
                                --from-literal=REDIS_PASSWORD="\$REDIS_PASSWORD" \\
                                -n ${K8S_NAMESPACE} \\
                                --save-config --dry-run=client -o yaml | kubectl apply -f -

                            kubectl create secret generic rabbitmq-secret \\
                                --from-literal=RABBITMQ_DEFAULT_USER=pharmtrack \\
                                --from-literal=RABBITMQ_DEFAULT_PASS="\$RABBITMQ_PASSWORD" \\
                                -n ${K8S_NAMESPACE} \\
                                --save-config --dry-run=client -o yaml | kubectl apply -f -

                            kubectl create secret generic gateway-app-secret \\
                                --from-literal=SECRET_KEY="\$DJANGO_SECRET_KEY" \\
                                -n ${K8S_NAMESPACE} \\
                                --save-config --dry-run=client -o yaml | kubectl apply -f -
                        """
                    }
                }
                stage('Apply Shared Infrastructure') {
                    steps {
                        sh """
                            export KUBECONFIG=\$KUBECONFIG_CRED
                            kubectl apply -f k8s/infra/10-postgres-gateway.yaml
                            kubectl apply -f k8s/infra/20-redis.yaml
                            kubectl apply -f k8s/infra/30-rabbitmq.yaml
                        """
                    }
                }
                stage('Wait & Connectivity Checks') {
                    steps {
                        sh """
                            export KUBECONFIG=\$KUBECONFIG_CRED
                            kubectl rollout status statefulset/postgres-gateway -n ${K8S_NAMESPACE} --timeout=180s || true
                            kubectl rollout status deployment/redis -n ${K8S_NAMESPACE} --timeout=120s || true
                            kubectl rollout status statefulset/rabbitmq -n ${K8S_NAMESPACE} --timeout=180s || true
                        """
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
                        anyOf { changeset "gateway/**"; branch 'main'; branch 'master' }
                    }
                    steps {
                        dir('gateway') {
                            sh """
                                docker build \\
                                    --label "git.commit=${env.GIT_COMMIT}" \\
                                    --label "build.number=${env.BUILD_NUMBER}" \\
                                    --label "branch=${env.BRANCH_NAME}" \\
                                    -t ${GATEWAY_IMAGE}:${IMAGE_TAG} \\
                                    -t ${GATEWAY_IMAGE}:latest \\
                                    .
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
                        anyOf { changeset "gateway/**"; branch 'main'; branch 'master' }
                    }
                    steps {
                        dir('gateway') {
                            sh """
                                docker run --rm \\
                                    -e SECRET_KEY=ci-lint-key \\
                                    -e DEBUG=True \\
                                    -e DB_PASSWORD=ci \\
                                    ${GATEWAY_IMAGE}:${IMAGE_TAG} \\
                                    flake8 . \\
                                        --max-line-length=120 \\
                                        --exclude=migrations,__pycache__,.venv \\
                                        --format=default
                            """
                        }
                    }
                }

                stage('Gateway - SAST (bandit)') {
                    when {
                        anyOf { changeset "gateway/**"; branch 'main'; branch 'master' }
                    }
                    steps {
                        dir('gateway') {
                            sh """
                                docker run --rm \\
                                    -e SECRET_KEY=ci-bandit-key \\
                                    -e DEBUG=True \\
                                    -e DB_PASSWORD=ci \\
                                    ${GATEWAY_IMAGE}:${IMAGE_TAG} \\
                                    bandit -r . \\
                                        --exclude ./.venv,./migrations \\
                                        -ll \\
                                        -f txt
                            """
                        }
                    }
                }

                stage('Gateway - Image Scan (Trivy)') {
                    when {
                        anyOf { changeset "gateway/**"; branch 'main'; branch 'master' }
                    }
                    steps {
                        sh """
                            docker run --rm \\
                                -v /var/run/docker.sock:/var/run/docker.sock \\
                                -v \$(pwd)/.trivy-cache:/root/.cache/ \\
                                aquasec/trivy:latest image \\
                                    --exit-code 1 \\
                                    --severity HIGH,CRITICAL \\
                                    --no-progress \\
                                    ${GATEWAY_IMAGE}:${IMAGE_TAG}
                        """
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
                        anyOf { changeset "gateway/**"; branch 'main'; branch 'master' }
                    }
                    steps {
                        dir('gateway') {
                            sh """
                                docker run --rm \\
                                    -e SECRET_KEY=ci-test-secret \\
                                    -e DEBUG=True \\
                                    -e DB_PASSWORD=ci \\
                                    -e DJANGO_SETTINGS_MODULE=pharmtrack_gateway.settings \\
                                    -v \$(pwd)/coverage.xml:/app/coverage.xml \\
                                    ${GATEWAY_IMAGE}:${IMAGE_TAG} \\
                                    pytest tests/ \\
                                        --tb=short -v \\
                                        --cov=. \\
                                        --cov-report=xml:/app/coverage.xml \\
                                        --cov-fail-under=70
                            """
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
                anyOf { branch 'main'; branch 'master' }
            }
            parallel {
                stage('Push Gateway') {
                    steps {
                        sh """
                            echo \$DOCKERHUB_CREDS_PSW | docker login -u \$DOCKERHUB_CREDS_USR --password-stdin
                            docker push ${GATEWAY_IMAGE}:${IMAGE_TAG}
                            docker push ${GATEWAY_IMAGE}:latest
                        """
                    }
                }
            }
        }

        // ==========================================
        // STAGE 7: Deploy to Kubernetes
        // ==========================================
        stage('Deploy to Kubernetes') {
            when {
                anyOf { branch 'main'; branch 'master' }
            }
            steps {
                script {
                    env.PREVIOUS_REVISION = sh(
                        script: """
                            export KUBECONFIG=\$KUBECONFIG_CRED
                            kubectl get deployment gateway -n ${K8S_NAMESPACE} \\
                                -o jsonpath='{.metadata.annotations.deployment\\.kubernetes\\.io/revision}' 2>/dev/null || echo '0'
                        """,
                        returnStdout: true
                    ).trim()
                }

                dir('gateway/k8s/base') {
                    sh """
                        export KUBECONFIG=\$KUBECONFIG_CRED
                        
                        sed 's#__IMAGE_TAG__#${IMAGE_TAG}#g' deployment.yaml  > deployment.rendered.yaml
                        sed 's#__IMAGE_TAG__#${IMAGE_TAG}#g' migrate-job.yaml > migrate-job.rendered.yaml

                        kubectl delete job gateway-migrate -n ${K8S_NAMESPACE} --ignore-not-found
                        kubectl apply -f migrate-job.rendered.yaml
                        kubectl wait --for=condition=complete job/gateway-migrate -n ${K8S_NAMESPACE} --timeout=120s

                        kubectl apply -f configmap.yaml
                        kubectl apply -f service.yaml
                        kubectl apply -f ingress.yaml
                        kubectl apply -f hpa.yaml
                        kubectl apply -f deployment.rendered.yaml

                        kubectl rollout status deployment/gateway -n ${K8S_NAMESPACE} --timeout=180s
                        rm -f deployment.rendered.yaml migrate-job.rendered.yaml
                    """
                }
            }
        }

        // ==========================================
        // STAGE 8: Smoke Test
        // ==========================================
        stage('Smoke Test') {
            when {
                anyOf { branch 'main'; branch 'master' }
            }
            steps {
                sh """
                    export KUBECONFIG=\$KUBECONFIG_CRED
                    kubectl run gateway-smoke-${env.BUILD_NUMBER} \\
                        -n ${K8S_NAMESPACE} \\
                        --rm -i \\
                        --restart=Never \\
                        --image=curlimages/curl:8.7.1 \\
                        -- curl -sf --retry 5 --retry-delay 3 \\
                             http://gateway.${K8S_NAMESPACE}.svc.cluster.local:8000/healthz/
                """
            }
        }
    }

    // ==========================================
    // POST / STAGE 9: Cleanup
    // ==========================================
    post {
        always {
            echo "Stage: Cleanup"
            sh "docker logout || true"
            sh "docker rmi ${GATEWAY_IMAGE}:${IMAGE_TAG} ${GATEWAY_IMAGE}:latest || true"
        }
        failure {
            script {
                // Trigger rollback if deployment failed
                if (env.PREVIOUS_REVISION && env.PREVIOUS_REVISION != '0') {
                    sh """
                        export KUBECONFIG=\$KUBECONFIG_CRED
                        echo "⚠️  Deploy failed — rolling back to revision ${env.PREVIOUS_REVISION}"
                        kubectl rollout undo deployment/gateway -n ${K8S_NAMESPACE} --to-revision=${env.PREVIOUS_REVISION} || true
                        kubectl rollout status deployment/gateway -n ${K8S_NAMESPACE} --timeout=120s || true
                    """
                }
            }
            emailext(
                subject: "Pipeline FAILED: \${env.JOB_NAME} - Build \${env.BUILD_NUMBER}",
                body: "Build \${env.BUILD_NUMBER} failed. View at: \${env.BUILD_URL}",
                to: "\${NOTIFY_EMAIL}"
            )
        }
        success {
            emailext(
                subject: "Pipeline SUCCESS: \${env.JOB_NAME} - Build \${env.BUILD_NUMBER}",
                body: "Build \${env.BUILD_NUMBER} succeeded successfully.",
                to: "\${NOTIFY_EMAIL}"
            )
        }
    }
}
