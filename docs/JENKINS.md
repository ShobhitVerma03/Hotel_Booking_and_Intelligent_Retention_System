# Jenkins CI/CD

Phase 13 validates the production Docker environment; it performs no deployment.
Jenkins checks out source, validates backend and frontend code, builds images,
starts an isolated Compose project, runs black-box smoke tests, archives safe
logs, and always removes the stack.

## Prerequisites

The current controller runs as a Windows service. Its selected agent needs Git,
Docker Desktop/Engine access, Docker Compose v2, Node.js/npm, and Python 3 on
the service account's PATH. Confirm that account can run `docker version`
before building. The declarative Jenkinsfile uses PowerShell steps and does not
require a Linux-only label. Required plugins: Pipeline, Git, Credentials
Binding, and Workspace Cleanup (plus JUnit or HTML Publisher if used).

Create a **Pipeline** job using **Pipeline script from SCM**, Git repository
`https://github.com/ShobhitVerma03/Hotel_Booking_and_Intelligent_Retention_System.git`,
branch `*/main`, and script path `Jenkinsfile`. The repository is public, so no
GitHub credential is required. Save, select **Build Now**, inspect Console
Output and archived logs, then optionally configure a webhook or SCM polling.

## Credentials

Create these **Secret text** credentials; their values are never committed or
printed:

- `hotel-ci-postgres-password`
- `hotel-ci-jwt-secret`
- `hotel-ci-manager-password`

`DEV_MANAGER_EMAIL` is a non-secret CI identifier. The smoke suite uses the
deterministic NL→SQL planner, so it does not require an LLM key. If a future CI
environment enables an LLM, store its key as a separate Jenkins secret.

## Pipeline stages

1. Checkout
2. Backend validation inside the production backend image (`compileall` and
   full unittest suite)
3. Customer frontend `npm ci`, tests, and production build
4. Manager frontend `npm ci`, tests, and production build
5. Compose configuration validation
6. Fresh Docker image build
7. Container startup, HTTP health polling, and Alembic revision check
8. Black-box smoke coverage: authentication, booking/cancellation,
   recommendation, approve/modify/reject HITL, RAG, and safe NL→SQL

The `post { always }` section archives a Compose log and runs
`docker compose down --volumes --remove-orphans` after success or failure.
The build uses a unique Compose project and synthetic CI customers, never a
production database.

## Troubleshooting

If startup times out, inspect `docker-compose.log`, Docker permissions for the
Windows service account, host ports `18000`, `18080`, `18081`, and registry
access. A command failure marks the build failed; do not weaken security.

The local Windows `.venv-ml` can fail two ML tests because Windows Application
Control blocks scikit-learn's `_gradient_boosting` native DLL. Jenkins does not
silence that issue. Linux/Docker CI runs the same RandomForest and RAG stack;
any Linux CI test failure is a real pipeline failure.

## Safety

Phase 13 does not deploy to Vercel, Render, Neon, or production. It does not
archive secrets, `.env` files, policy PDFs, Chroma databases, or database
volumes.
