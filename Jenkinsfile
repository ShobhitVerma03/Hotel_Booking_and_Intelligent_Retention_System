pipeline {
    agent { label 'docker' }

    options {
        timestamps()
        disableConcurrentBuilds()
        skipDefaultCheckout(true)
        timeout(time: 60, unit: 'MINUTES')
    }

    environment {
        BACKEND_PORT = '18000'
        CUSTOMER_FRONTEND_PORT = '18080'
        MANAGER_FRONTEND_PORT = '18081'
        DEV_MANAGER_EMAIL = 'manager@example.com'
        NL_SQL_LLM_ENABLED = 'false'
        COMPOSE_PROJECT_NAME = "hotel-ci-${BUILD_NUMBER}"
        BACKEND_CI_IMAGE = "hotel-platform-backend-ci:${BUILD_NUMBER}"
    }

    stages {
        stage('Checkout') {
            steps { checkout scm }
        }

        stage('Backend Validation') {
            steps {
                sh '''
                    set -eu
                    # This is the production backend image, not a host virtualenv.
                    docker build -f backend/Dockerfile -t "$BACKEND_CI_IMAGE" .
                    docker run --rm --entrypoint sh "$BACKEND_CI_IMAGE" -c '
                        python -m compileall -q backend
                        python -m unittest discover -s backend/tests -v
                    ' | tee backend-test.log
                '''
            }
        }

        stage('Customer Frontend Validation') {
            steps {
                dir('frontend/customer') {
                    sh '''
                        set -eu
                        npm ci
                        npm test
                        npm run build
                    '''
                }
            }
        }

        stage('Manager Frontend Validation') {
            steps {
                dir('frontend/manager') {
                    sh '''
                        set -eu
                        npm ci
                        npm test
                        npm run build
                    '''
                }
            }
        }

        stage('Docker Compose Configuration Validation') {
            steps {
                withCredentials([
                    string(credentialsId: 'hotel-ci-postgres-password', variable: 'POSTGRES_PASSWORD'),
                    string(credentialsId: 'hotel-ci-jwt-secret', variable: 'JWT_SECRET_KEY'),
                    string(credentialsId: 'hotel-ci-manager-password', variable: 'DEV_MANAGER_PASSWORD')
                ]) {
                    sh 'docker compose config --quiet'
                }
            }
        }

        stage('Docker Image Build') {
            steps {
                withCredentials([
                    string(credentialsId: 'hotel-ci-postgres-password', variable: 'POSTGRES_PASSWORD'),
                    string(credentialsId: 'hotel-ci-jwt-secret', variable: 'JWT_SECRET_KEY'),
                    string(credentialsId: 'hotel-ci-manager-password', variable: 'DEV_MANAGER_PASSWORD')
                ]) {
                    sh 'docker compose build'
                }
            }
        }

        stage('Container Startup') {
            steps {
                withCredentials([
                    string(credentialsId: 'hotel-ci-postgres-password', variable: 'POSTGRES_PASSWORD'),
                    string(credentialsId: 'hotel-ci-jwt-secret', variable: 'JWT_SECRET_KEY'),
                    string(credentialsId: 'hotel-ci-manager-password', variable: 'DEV_MANAGER_PASSWORD')
                ]) {
                    sh '''
                        set -eu
                        docker compose up -d
                        python3 docker/ci_wait_for_services.py
                        docker compose exec -T backend python -m alembic -c /app/backend/alembic.ini current
                    '''
                }
            }
        }

        stage('Integration and Smoke Tests') {
            steps {
                withCredentials([
                    string(credentialsId: 'hotel-ci-postgres-password', variable: 'POSTGRES_PASSWORD'),
                    string(credentialsId: 'hotel-ci-jwt-secret', variable: 'JWT_SECRET_KEY'),
                    string(credentialsId: 'hotel-ci-manager-password', variable: 'DEV_MANAGER_PASSWORD')
                ]) {
                    sh 'python3 docker/ci_smoke_test.py | tee integration-smoke.log'
                }
            }
        }
    }

    post {
        always {
            script {
                withCredentials([
                    string(credentialsId: 'hotel-ci-postgres-password', variable: 'POSTGRES_PASSWORD'),
                    string(credentialsId: 'hotel-ci-jwt-secret', variable: 'JWT_SECRET_KEY'),
                    string(credentialsId: 'hotel-ci-manager-password', variable: 'DEV_MANAGER_PASSWORD')
                ]) {
                    sh '''
                        docker compose logs --no-color > docker-compose.log || true
                        docker compose down --volumes --remove-orphans || true
                    '''
                }
            }
            archiveArtifacts artifacts: 'backend-test.log,integration-smoke.log,docker-compose.log', allowEmptyArchive: true
        }
        success { echo 'CI validation completed successfully.' }
        failure { echo 'CI validation failed; safe logs are archived when available.' }
    }
}
