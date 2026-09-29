pipeline {
    // The controller runs as a Windows service. Any selected agent needs Git,
    // Docker access, Docker Compose v2, Python 3, Node.js, and npm.
    agent any

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
        POSTGRES_DB = 'hotel_platform_ci'
        POSTGRES_USER = 'hotel_platform_ci'
        DEV_MANAGER_EMAIL = 'manager@example.com'
        NL_SQL_LLM_ENABLED = 'false'
        COMPOSE_PROJECT_NAME = "hotel-ci-${BUILD_NUMBER}"
        BACKEND_CI_IMAGE = "hotel-platform-backend-ci:${BUILD_NUMBER}"

        DOCKER_BUILDKIT = '1'
        COMPOSE_DOCKER_CLI_BUILD = '1'
    }

    stages {
        stage('Checkout') { steps { checkout scm } }

        stage('Backend Validation') {
            steps {
                powershell '''
                    $ErrorActionPreference = 'Stop'
                    docker build -f backend/Dockerfile -t $env:BACKEND_CI_IMAGE .
                    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
                    docker run --rm --entrypoint sh $env:BACKEND_CI_IMAGE -c "python -m compileall -q backend && python -m unittest discover -s backend/tests -v" | Tee-Object -FilePath backend-test.log
                    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
                '''
            }
        }

        stage('Customer Frontend Validation') {
            steps {
                dir('frontend/customer') {
                    powershell '''
                        $ErrorActionPreference = 'Stop'
                        npm ci; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
                        npm test; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
                        npm run build; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
                    '''
                }
            }
        }

        stage('Manager Frontend Validation') {
            steps {
                dir('frontend/manager') {
                    powershell '''
                        $ErrorActionPreference = 'Stop'
                        npm ci; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
                        npm test; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
                        npm run build; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
                    '''
                }
            }
        }

        stage('Docker Compose Configuration Validation') {
            steps { script { withCiSecrets { powershell 'docker compose config | Out-Null; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }' } } }
        }

        stage('Docker Image Build') {
            steps { script { withCiSecrets { powershell 'docker compose build; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }' } } }
        }

        stage('Container Startup') {
            steps {
                script { withCiSecrets {
                    powershell '''
                        $ErrorActionPreference = 'Stop'
                        function Exit-WithStartupDiagnostics([int]$startupStatus) {
                            $ErrorActionPreference = 'Continue'
                            docker compose ps
                            docker compose logs --tail=200 backend
                            docker compose logs --tail=100 postgres
                            exit $startupStatus
                        }
                        docker compose up -d; if ($LASTEXITCODE -ne 0) { Exit-WithStartupDiagnostics $LASTEXITCODE }
                        python docker/ci_wait_for_services.py; if ($LASTEXITCODE -ne 0) { Exit-WithStartupDiagnostics $LASTEXITCODE }
                        docker compose exec -T backend python -m alembic -c /app/backend/alembic.ini current
                        if ($LASTEXITCODE -ne 0) { Exit-WithStartupDiagnostics $LASTEXITCODE }
                    '''
                } }
            }
        }

        stage('Integration and Smoke Tests') {
            steps {
                script { withCiSecrets {
                    powershell '''
                        $ErrorActionPreference = 'Stop'
                        python docker/ci_smoke_test.py | Tee-Object -FilePath integration-smoke.log
                        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
                    '''
                } }
            }
        }
    }

    post {
        always {
            script { withCiSecrets {
                def cleanupStatus = powershell(returnStatus: true, script: '''
                    $ErrorActionPreference = 'Continue'
                    docker compose logs | Out-File -FilePath docker-compose.log -Encoding utf8
                    $logsStatus = $LASTEXITCODE
                    docker compose down -v --remove-orphans
                    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
                    exit $logsStatus
                ''')
                if (cleanupStatus != 0) { echo "WARNING: Compose log collection or cleanup failed (exit ${cleanupStatus}); preserving the pipeline result." }
            } }
            archiveArtifacts artifacts: 'backend-test.log,integration-smoke.log,docker-compose.log', allowEmptyArchive: true
        }
        success { echo 'CI validation completed successfully.' }
        failure { echo 'CI validation failed; safe logs are archived when available.' }
    }
}

def withCiSecrets(Closure body) {
    withCredentials([
        string(credentialsId: 'hotel-ci-postgres-password', variable: 'POSTGRES_PASSWORD'),
        string(credentialsId: 'hotel-ci-jwt-secret', variable: 'JWT_SECRET_KEY'),
        string(credentialsId: 'hotel-ci-manager-password', variable: 'DEV_MANAGER_PASSWORD')
    ]) {
        body()
    }
}
