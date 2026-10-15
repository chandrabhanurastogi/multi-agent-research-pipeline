# Non-Functional Requirements

What "production-ready" means for this service, as testable targets. Each requirement names how it is verified and the step that delivers it (see [`PRODUCTION_PLAN.md`](PRODUCTION_PLAN.md)).

**Status: proposed.** Targets are a starting point to agree with the product owner, analysts, compliance and the platform teams. Numbers marked *(measure)* are set after the step that first measures them.

**Baseline (take-home, from `examples/`):** a run takes about 20 s of model time over 6–7 steps and uses about 5–10k tokens, against a 12-document corpus. A real corpus and parallel research will change both; A5 measures them.

---

## 1. Workload and capacity

| ID | Requirement | Target | Verified by | Step |
|---|---|---|---|---|
| CAP-1 | Concurrent runs in progress | 20 per environment, limited by gateway quota, not by pods | Load test in stage | A2, B |
| CAP-2 | Runs per day | 500 in prod | Load test in stage | B |
| CAP-3 | Question length | 5–1000 characters (as today) | API validation test | A2 |
| CAP-4 | Back-pressure when quota or capacity is exhausted | Requests are queued, never dropped; API returns `202` with position, or `429` with `Retry-After` when the queue is full | Integration test | A2 |

## 2. Latency

| ID | Requirement | Target | Verified by | Step |
|---|---|---|---|---|
| LAT-1 | API response to submit a run | p95 < 300 ms (run is asynchronous) | Load test | A2 |
| LAT-2 | Run completion, excluding time waiting for human plan approval | p95 < 3 min, p50 < 90 s *(measure)* | Langfuse / metrics | A5 |
| LAT-3 | Hard limit per run | Run times out at 10 min and is marked failed with its state saved | Integration test | A2 |

## 3. Availability and reliability

| ID | Requirement | Target | Verified by | Step |
|---|---|---|---|---|
| REL-1 | API availability | 99.5% monthly in business hours (internal analyst tool) | SLO dashboard | C |
| REL-2 | No accepted run is lost | A run accepted with `202` always ends as `completed`, `failed` or `cancelled`, even if pods restart | Chaos test: kill worker mid-run | A2, A7 |
| REL-3 | Crash recovery | A run interrupted by a crash resumes from its last finished step; finished LLM calls are not repeated | Chaos test | A7 |
| REL-4 | Duplicate protection | The same `Idempotency-Key` returns the same run; a job delivered twice runs once | Integration test | A2 |
| REL-5 | Dependency failure | Gateway, search or database outage fails runs fast with a clear status (circuit breaker); no hung workers | Fault-injection test | A4 |
| REL-6 | Zero-downtime deploy | Rolling update; in-flight runs finish or resume | Deploy test in stage | B, C |
| REL-7 | Backup and restore | Postgres RPO ≤ 24 h, RTO ≤ 4 h | Restore drill | C |

## 4. Cost

| ID | Requirement | Target | Verified by | Step |
|---|---|---|---|---|
| COST-1 | Cost per run is measured and attributed | Every run records tokens and cost per step | Run record, Langfuse | A5 |
| COST-2 | Budget per run | Configurable cap on LLM calls (default 15) and tokens (default 100k); exceeding it stops the run with a clear status | Integration test | A2 |
| COST-3 | Monthly budget | Set with the gateway team; alert at 80% *(measure)* | Gateway / dashboard | B, C |

## 5. Answer quality

| ID | Requirement | Target | Verified by | Step |
|---|---|---|---|---|
| QUAL-1 | No invented quotes in a briefing | 100%: every quote in a briefing appears word-for-word in its source (enforced by the trust boundary) | Deterministic eval check | A6 |
| QUAL-2 | Known disagreements are reported | 100% of golden-set disagreements appear in the briefing | Golden set | A6 |
| QUAL-3 | Known gaps are reported, not filled from model memory | 100% of golden-set gaps appear as gaps | Golden set | A6 |
| QUAL-4 | Prompt injection in documents has no effect | 100% of injection cases ignored | Golden set | A6 |
| QUAL-5 | No regression | Every prompt, model, search or orchestration change scores ≥ the committed baseline on the golden set (within a tolerance set in A6) | Evaluation gate in CI | A6, B |
| QUAL-6 | Human review | Briefings flagged `review_required` are visibly marked; a sample of high-impact briefings is reviewed by analysts | Process + UI marker | C |

## 6. Security

| ID | Requirement | Target | Verified by | Step |
|---|---|---|---|---|
| SEC-1 | Authentication | Every API call requires a valid OIDC token; health endpoints excepted | API tests | A2 |
| SEC-2 | Authorisation | A user can read only their own runs (or their team's, if configured) | API tests | A2 |
| SEC-3 | Document entitlements | Search returns only documents the user's groups may see; filter applied inside the search query | Entitlement tests | A8 |
| SEC-4 | Secrets | No secret in code, image, logs or ConfigMaps; secrets from Vault in clusters; provider LLM keys never in this service | `gitleaks`, image scan, review | A1, A4, B |
| SEC-5 | Dependencies and image | No known critical vulnerabilities at release; SBOM produced per image | `pip-audit`, image scan | A1, B |
| SEC-6 | Container | Non-root arbitrary UID, read-only root filesystem, no privilege escalation | OpenShift restricted SCC | A2, B |
| SEC-7 | Network | Egress only to declared dependencies | NetworkPolicy | B |
| SEC-8 | Untrusted content | Documents passed to models as delimited data; models never set IDs, tiers or scores (as today) | Golden-set injection cases | A6 |
| SEC-9 | PII | Personal data detected and masked before reaching the LLM or logs | PII test cases | A9 |

## 7. Data, audit and compliance

| ID | Requirement | Target | Verified by | Step |
|---|---|---|---|---|
| DATA-1 | Audit trail per run | Who asked, when, question, plan, sources used, models and prompt versions per step, verdicts, scores, final briefing | Run record schema test | A3 |
| DATA-2 | Retention | Run records 1 year, artifacts 90 days, then deleted *(agree with compliance)* | Scheduled job test | A3 |
| DATA-3 | Model data usage | Only models approved by the gateway team, under terms that exclude training on our data | Gateway onboarding | B |
| DATA-4 | Data residency | Data and model calls stay in the approved region *(agree with compliance)* | Gateway / platform config | B |
| DATA-5 | Logs | No question text, document text or prompts in logs by default; logs carry IDs only | Log review test | A1 |

## 8. Observability

| ID | Requirement | Target | Verified by | Step |
|---|---|---|---|---|
| OBS-1 | Tracing | One trace per run, a span per step and per LLM call; trace ID in API responses and logs | Manual check in Langfuse | A5 |
| OBS-2 | Metrics | Runs by status, duration, tokens, cost, fallback rate, trust-boundary rejection rate, unverified rate | Dashboard | A5 |
| OBS-3 | Alerts | Failure rate, p95 latency, fallback rate, quota, cost against budget | Alert rules | C |
| OBS-4 | Logs | Structured JSON to stdout with `run_id` and trace ID on every line | Log format test | A1 |

## 9. Operability and maintainability

| ID | Requirement | Target | Verified by | Step |
|---|---|---|---|---|
| OPS-1 | Configuration | All environment differences are configuration; settings validated at startup; invalid config stops the service | Startup test | A1 |
| OPS-2 | Model changes | Changing a model is a gateway / config change, released through the pipeline | Review | A4, B |
| OPS-3 | Rollback | Previous image + previous config restores previous behaviour; migrations backward compatible | Rollback drill in stage | A3, C |
| OPS-4 | Runbook | Covers stuck runs, quota exhaustion, gateway outage, bad release, restore | Review | C |
| MNT-1 | Code quality | `ruff`, `mypy --strict` clean on `src/`; one command runs all checks locally and in CI | `make` targets | A1 |
| MNT-2 | Tests | All workflow branches tested offline; integration tests with real Postgres/MinIO (Testcontainers) | CI | A1, A3 |
| MNT-3 | Decisions recorded | Each significant decision has an ADR in [`adr/`](adr/) | Review | ongoing |
