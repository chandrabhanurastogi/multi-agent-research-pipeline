# Production Plan

How the take-home pipeline becomes a production service. This is the resume point: read **Status** first, then the next unchecked step.

- **Take-home version (frozen):** branch `take-home`, tag `v0.1.0-takehome`.
- **Production line:** `main`.

---

## Status

| Phase | Step | State |
|---|---|---|
| 0 | Freeze take-home on branch + tag | ✅ done (2026-10-14, `6f9ad39`) |
| A | A0 Non-functional requirements and ADRs | ⬜ next |
| A | A1 Project foundation | ⬜ |
| A | A2 Service shape: API, worker, queue, auth | ⬜ |
| A | A3 Persistence: Postgres + object storage | ⬜ |
| A | A4 LLM gateway | ⬜ |
| A | A5 Observability | ⬜ |
| A | A6 Evaluation harness and baseline | ⬜ |
| A | A7 LangGraph orchestration | ⬜ |
| A | A8 Document ingestion and hybrid search | ⬜ |
| A | A9 Guardrails and session memory | ⬜ |
| B | Infrastructure (Jenkins, Helm, Vault, OpenShift) | ⬜ |
| C | Wire application to infrastructure, promote to prod | ⬜ |

Update this table in the same commit that finishes a step.

---

## Guiding principle

**The code is production code from the first commit. Only configuration differs between a laptop and prod.**

| Allowed to differ per environment | Never differs |
|---|---|
| Endpoints (`DATABASE_URL`, `LLM_GATEWAY_URL`, ...) | Code paths: no `if env == "prod"` |
| Credentials (from `.env` locally, Vault in clusters) | Container image: one image, promoted unchanged |
| Model pins, thresholds, replica counts, log level | Database schema (same migrations everywhere) |
| Feature flags with a documented default | Dependencies (same lock file) |

Example: locally `DATABASE_URL=postgresql://app@localhost:5432/research`; in prod Vault injects the real URL. The code that reads it, the migrations it runs and the image it runs in are identical.

---

## Phases

1. **Phase A: application production-ready, running locally** with `docker compose up`, using the same technologies as production (not lighter substitutes).
2. **Phase B: infrastructure**, proven with a trivial image, no application logic.
3. **Phase C: wire them together.** Configuration only. If Phase C needs a code change, Phase A missed something.

### Local stand-ins (same technology as production)

| Concern | Local (docker-compose) | Production | Owner in production |
|---|---|---|---|
| Run records, checkpoints, job queue | Postgres | Managed Postgres | Platform / DBA team |
| Briefings and run artifacts | MinIO (S3 API) | S3 / OpenShift Data Foundation | Platform team |
| LLM access | LiteLLM proxy in front of Gemini | Enterprise LLM gateway | AI platform team |
| Search | OpenSearch | OpenSearch cluster | Search platform team |
| Tracing and LLM cost | Langfuse + OpenTelemetry collector | Shared Langfuse / observability platform | Observability team |
| User identity | Keycloak (OIDC) | Corporate identity provider (OIDC) | Identity team |
| Secrets | `.env` file read by docker-compose (never by code) | Vault | Our team (our credentials only) |

### Credentials: who owns what

- **LLM provider keys belong to the AI platform team**, inside the gateway; ideally there is no static key at all (managed identity / IAM role / service account). Our service never sees them.
- **Our service holds only its credential for the gateway** (a scoped virtual key, OAuth2 client credentials, or nothing with workload identity). It is read in one function, so moving to workload identity later changes only that function.
- Locally, the Gemini key goes into the LiteLLM container only.

---

## Phase A steps

Each step: one or more small commits on `main`; all tests green; `README.md` and this file updated; `docs/CONTROL_FLOW.md` refreshed (local file).

### A0. Non-functional requirements and ADRs
Write down what "production-ready" means before building it.
- `docs/NFR.md`: target latency per run (e.g. p95 < 3 min), availability, max cost per run, concurrent runs, data retention, audit needs.
- `docs/adr/`: one short Architecture Decision Record per decision below (context, decision, alternatives, consequences).

**Done when:** NFRs and ADRs for the open decisions are written and agreed.

### A1. Project foundation
- Python **3.12** pinned (`.python-version`); UBI images ship 3.12, local venv currently runs 3.14.
- Dependency lock file with **uv** (`uv.lock`); package index URL configurable for an internal mirror (Artifactory).
- `ruff` (lint + format), `mypy --strict` on `src/`, `pre-commit`.
- Security checks runnable locally: `pip-audit` (dependencies), `bandit` (code), `gitleaks` (secrets).
- One `Settings` class (`pydantic-settings`) for all configuration; replaces scattered `os.getenv`; **validated at startup**, so a missing or invalid value fails fast. The fake LLM is refused unless `APP_ENV=local|test`.
- Structured JSON logging to stdout with a `run_id` / correlation ID on every line; no prompt or document text in logs by default.
- `Makefile` targets (`lint`, `typecheck`, `test`, `security`, `build`) so Jenkins later calls exactly what developers run.
- Semantic versioning, `CHANGELOG.md`, conventional commits (already in use).

**Done when:** `make lint typecheck test security` passes; the CLI still produces the same briefing.

### A2. Service shape: API, worker, queue, authentication
- **API** (FastAPI), versioned: `POST /v1/runs` (returns `run_id`, accepts an `Idempotency-Key`), `GET /v1/runs/{id}`, `GET /v1/runs/{id}/briefing`; `/healthz`, `/readyz`; OpenAPI spec committed; one error format.
- **Authentication from day one:** OIDC JWT validation (Keycloak locally); the user ID is recorded on every run (needed later for entitlements and audit).
- **Worker** as a separate process, pulling jobs from a **durable queue** (decision ADR-4); graceful shutdown; a run picked up twice does not run twice.
- Per-run limits: timeout, max LLM calls, max tokens/cost budget.
- **Container:** UBI Python base, runs as an arbitrary non-root UID, read-only root filesystem (writes only to `/tmp`), no secrets in the image, healthcheck.
- `docker-compose.yml`: api, worker, Postgres, Keycloak (more services added by later steps).
- CLI kept as an admin/debug tool calling the same workflow.

**Done when:** `docker compose up`, get a token from Keycloak, submit a question, poll, read the briefing — all through the API.

### A3. Persistence: Postgres + object storage
- Run records and step traces in Postgres (JSONB for `RunState`), **Alembic** migrations, backward compatible so a rollback can still read new rows.
- `briefing.md` and full run artifacts in MinIO; the database stores the object key.
- Retention setting (e.g. delete artifacts after N days) and audit fields (who, when, which models and prompt versions).
- Integration tests with **Testcontainers** (real Postgres and MinIO in tests).

**Done when:** runs survive a restart of every container; `runs/` directory no longer used.

### A4. LLM gateway
- LiteLLM proxy container; Gemini key only in its config.
- Agents call the gateway through Pydantic AI's OpenAI-compatible provider; **per-agent model aliases** (`planner-default`, `verifier-default`) mapped to real models in the gateway.
- Fallback chain moves into the gateway (models and order) or stays in the app (decision ADR-5); either way the model that answered is still recorded per step.
- Timeouts, retries with backoff on 429/5xx, and a circuit breaker so a gateway outage fails fast.
- Policy: in `stage`/`prod`, refuse to publish if a critical step (Synthesiser, Verifier) ran on a fallback model (setting, default on).

**Done when:** no provider key in the app's environment; switching a model is a gateway config change.

### A5. Observability
- OpenTelemetry traces: one trace per run, one span per step and per LLM call; exported to Langfuse locally.
- Metrics: runs by status, duration, tokens and cost per run, fallback rate, trust-boundary rejection rate, unverified rate.
- Trace ID returned in API responses and written to logs.

**Done when:** one run can be followed end to end in Langfuse with its cost.

### A6. Evaluation harness and baseline
Comes **before** any change that can affect answer quality (A7–A9, model changes).
- Versioned golden set in `eval/`: questions with expected findings, expected disagreements (e.g. orderbook 7% vs 10%), expected gaps (ship financing), and injection cases (S12).
- Deterministic checks (gaps reported, injection ignored, no invented quotes) plus LLM-as-judge metrics (decision ADR-7: e.g. Ragas, DeepEval or promptfoo).
- `make eval` produces a scored report; the current pipeline's score is committed as the **baseline**.

**Done when:** a baseline report exists and a deliberately broken prompt makes `make eval` fail.

### A7. LangGraph orchestration
- Workflow steps become graph nodes; agents (Pydantic AI) unchanged.
- Postgres checkpointer: a crashed run resumes from its last finished step.
- Plan approval: optional `interrupt()` after the Planner, exposed as `POST /v1/runs/{id}/plan/approve`.
- Researchers run in parallel, one per sub-question.

**Done when:** killing the worker mid-run and restarting it finishes the same run without repeating completed LLM calls; `make eval` is not worse than baseline.

### A8. Document ingestion and hybrid search
- Ingestion job: loads documents into OpenSearch with a **source registry** (tier, primary origin, date, access group) as governed data, not code.
- Hybrid search (keyword + vector) with a reranker, behind the existing `search()` interface.
- **Entitlement filter inside the search query**: a user only retrieves documents their groups may see.

**Done when:** BM25 removed; a user without access to a document never sees it in claims or briefing; `make eval` not worse than baseline.

### A9. Guardrails and session memory
- Input and output guardrails (decision ADR-8), PII detection (e.g. Presidio) before text reaches the LLM or logs.
- Session memory: follow-up questions on a run ("dig into point 3"), stored per user and session via the LangGraph thread; no unreviewed long-term model memory.

**Done when:** guardrail and PII test cases pass in `make eval`; follow-up questions work through the API.

---

## Phase B: infrastructure (outline, detailed when Phase A is done)

- **Jenkinsfile** (generic; adapt to the organisation's shared library): `make lint typecheck test security` → image build → image scan + SBOM → push to registry → `helm upgrade` per branch. Evaluation gate in sit/stage.
- **Branch to environment:** `feature/*` → dev, `develop` → sit, `release/x.y` → release candidate → stage, tag `vX.Y.Z` → prod. One image, promoted by digest, never rebuilt.
- **Helm chart** `deploy/helm/research-pipeline/`: api and worker Deployments, ConfigMap, ServiceAccount, Service, Route (TLS, api only), NetworkPolicy (egress only to gateway, Postgres, object storage, OpenSearch, telemetry, identity provider), HPA for the worker capped by gateway quota, PodDisruptionBudget, probes, resource limits; `values-{dev,sit,stage,prod}.yaml`.
- **Vault:** paths for our credentials only (database, object storage, gateway client credential, Langfuse); injected via Vault Agent or External Secrets.
- **Requests to other teams:** namespaces, gateway onboarding (team key / client ID, model aliases, budget), Postgres and object storage instances, OpenSearch index access, OIDC client registration, Langfuse project.

**Done when:** a "hello" image deploys through dev → sit → stage → prod by the same pipeline.

## Phase C: wire together (outline)

- Point each environment's values at the real endpoints; move secrets into Vault; run migrations as a Helm hook or init job.
- Smoke test after every deploy; evaluation gate before stage → prod.
- Runbook, SLOs and alerts, backup and restore of Postgres, rollback procedure (previous image + previous ConfigMap).
- Analyst and compliance sign-off in stage; canary or shadow mode in prod.

---

## Decisions

### Made
| # | Decision | Date |
|---|---|---|
| D1 | Same repo; `main` is the production line; take-home frozen on branch `take-home` + tag `v0.1.0-takehome` | 2026-10-14 |
| D2 | Our service never holds LLM provider keys; it calls an enterprise LLM gateway with its own scoped credential | 2026-10-14 |
| D3 | Pydantic AI inside each agent (typed contracts, validation retry); LangGraph for orchestration (checkpoints, approval, resume) | 2026-10-14 |
| D4 | Phases: A application (local, same tech as prod) → B infrastructure → C wiring; environment differences are configuration only | 2026-10-15 |
| D5 | Generic Jenkins / Helm / Vault templates, to be adapted to organisation conventions | 2026-10-14 |

### Open (one ADR each, decided at the step that needs it)
| ADR | Question | Needed by | Leaning |
|---|---|---|---|
| ADR-1 | Package manager | A1 | uv |
| ADR-2 | Settings and secrets loading | A1 | pydantic-settings, env vars only |
| ADR-3 | Identity provider locally | A2 | Keycloak |
| ADR-4 | Job queue for the worker | A2 | Postgres-backed queue (no extra broker); RabbitMQ/Kafka if the organisation standardises on one |
| ADR-5 | Fallback chain in gateway or app | A4 | gateway, app still records the answering model |
| ADR-6 | Tracing backend | A5 | Langfuse via OpenTelemetry |
| ADR-7 | Evaluation framework | A6 | promptfoo or DeepEval, plus our deterministic checks |
| ADR-8 | Guardrail service | A9 | to evaluate: Guardrails AI, NeMo Guardrails, cloud provider guardrails |
| ADR-9 | Embedding model and reranker | A8 | via the gateway, to evaluate on the golden set |
