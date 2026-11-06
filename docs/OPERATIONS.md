# Delivery and Operations

How changes reach production safely, how the system is tested, what fails in production and what to do about it. It supports MNT, OPS and QUAL in [NFR.md](NFR.md) and Phases B and C of [PRODUCTION_PLAN.md](PRODUCTION_PLAN.md).

---

## 1. Pipeline

```
commit ─► make lint typecheck test security ─► build image ─► scan + SBOM ─► push (by digest)
       ─► dev ─► sit (contract tests, eval gate if quality-affecting) ─► stage (load, eval, chaos)
       ─► prod: shadow ─► canary 1% ─► 5% ─► 25% ─► 100%
```

- One image, built once, promoted by digest. Environments differ only by Helm values and Vault (ADR 0004).
- Jenkins calls the same `make` targets developers run locally.
- Prod promotion needs an approval and a green evaluation report.

### Known risks and how the pipeline handles them

| Risk | Cause | Control |
|---|---|---|
| Flaky evaluation gate | Model output varies between runs | Deterministic checks are hard gates; judge scores use N repeats and a tolerance band against the committed baseline; temperature 0 where the model allows |
| Evaluation cost and quota in CI | Every run calls real models | Offline fake-model tests on every commit; the real evaluation runs when prompts, models, retrieval or orchestration change (path filters), and nightly; CI has its own gateway budget |
| Prompt change merged without evaluation | Prompts look like plain strings | Prompts live in `llm/prompts.py` with version strings; a change there makes the eval gate mandatory; the version is recorded on every run |
| Fake model drifts from real behaviour | Offline fakes never return what the real model does | Contract tests against the gateway in sit; recorded real responses replayed as fixtures |
| Model changes behind a stable name | "Latest" aliases | Versions pinned at the gateway; nightly golden set against prod configuration |
| Python or dependency mismatch | Local 3.14, image 3.12 | `.python-version` pinned; `uv.lock`; CI and image use the same interpreter |
| Image rebuilt per environment | Different bits in prod than in stage | Build once, promote by digest |
| Migration breaks rollback | New code writes what old code cannot read | Expand/contract migrations, backward compatible; run as a Helm hook with the migration role (OPS-3) |
| Secrets in logs or images | Debug output, `.env` copied in | `gitleaks` in pre-commit and CI; `.dockerignore`; secrets injected at runtime only |
| Long-lived CI credentials | Tokens stored in Jenkins for years | Short-lived, per-environment tokens; prod deploy identity separate |
| Deploy interrupts runs | Rolling update terminates workers mid-run | Graceful shutdown releases the job; checkpoints let the next worker resume (REL-6, A7) |
| Helm values drift | Hand edits per environment | Values in git, schema-validated, diff shown before upgrade |

---

## 2. Releasing a prompt, model or retrieval change

1. Change the prompt (and its version) or the gateway alias mapping in a PR.
2. CI runs the offline tests, then the golden-set evaluation.
3. The report compares against the committed baseline: deterministic checks must stay at 100%, and judge scores within tolerance.
4. **Shadow in prod:** the new configuration runs on a copy of a small share of real requests; results are compared and not shown to users.
5. **Canary:** 1% → 5% → 25% → 100%, holding at each step until rejection rate, retry rate, review-required rate, cost per run and user feedback are within bounds.
6. **Rollback:** the previous image plus the previous configuration. The prompt version on every run identifies exactly which briefings a bad release produced.

---

## 3. Testing

Tests with a fake model prove the system **behaves** correctly. The evaluation set proves the answers are **good**. Both are required.

| Layer | Proves | Status |
|---|---|---|
| Policy unit tests | Trust boundary, sufficiency, source quality, confidence rules, including worked examples | ✅ |
| Agent tests (Pydantic AI `FunctionModel`) | What each agent is shown; retry on invalid output | ✅ |
| Workflow branch tests (injected fake agents) | Every failure path: planner fails, researcher fails, no evidence, synthesis fails, verifier fails, one revision, fallback warning, bugs not swallowed | ✅ |
| Integration (Testcontainers) | Queue, migrations, checkpoints, object storage | A2, A3 |
| API and auth tests | Token validation, per-user access, idempotency, back-pressure | A2 |
| Contract tests | Gateway responses match what we parse, including the answering model | A4 |
| Entitlement tests | Restricted documents never reach claims, briefings or the cache | A8 |
| Golden-set evaluation | Expected findings, disagreements, gaps; injection ignored | A6 |
| Adversarial cases | Injection in documents and questions, PII, disallowed content | A6, A9 |
| Load | Peak B for 1 h, burst to peak C ([CAPACITY.md](CAPACITY.md)) | Phase C |
| Chaos and fault injection | Worker kill, gateway region loss, database failover | Phase C |

**Every production defect becomes a deterministic test** of the code around the model, or a golden-set case for the model's behaviour. Three of the confidence rules were found this way: copies counting as independent confirmation, attribution hiding a disagreement, and a blended score hiding strong findings.

---

## 4. Failure modes

| Failure | Detected by | Response |
|---|---|---|
| Model quota exhausted / 429 storm | `gateway_responses_total{code="429"}`, queue age | Queue, never drop (CAP-4); concurrency sized to quota; backoff with jitter; admission returns `429` + `Retry-After` |
| Fallback model lowers quality | `llm_fallback_total`; rejection and retry rates | Answering model recorded; Verifier-on-fallback briefings held for review |
| Thundering herd after gateway recovery | 429 spike after an outage | Circuit breaker half-open probing; jittered retries; cap on concurrent claims |
| Worker crash mid-run | Lease expiry; duplicate token cost per `run_id` | Checkpoints; idempotent job execution; lease-based claiming |
| Poison job | Same job retried repeatedly | Maximum attempts, then dead-letter with state saved; alert |
| Prompt injection in new documents | Golden-set injection cases; unusual verdicts | The model has no authority over scores; gateway guardrails; ingestion review |
| Entitlement drift | Access reviews; audit of sources against user groups | Filter in search; re-check on read; short-lived delegated tokens |
| Model deprecation | Provider notice; errors on an alias | Pinned versions with an upgrade calendar; evaluation of the replacement |
| Cost spike | `run_cost` tail; budget alert | Per-run caps; find oversized inputs; check cache hit rate |
| Latency long tail | p95 / p50 gap | Parallel researchers; per-step timeouts; model tiering |
| Corpus misses demand | Gap ratio, insufficient-evidence rate | Report to content owners; product signal, not a defect |
| Over-trust in scores | Feedback and review findings | Wording "by our sources"; sources and gaps shown; review flags |
| PII in telemetry | DLP scan, log review | Content off by default; Collector redaction; masking before the model |
| Postgres saturation from checkpoints | DB CPU, write latency, vacuum lag | Small checkpoints; prune on completion; partitioning; ADR 0015 trigger to move the queue |

---

## 5. Runbook (OPS-4)

### Stuck runs
1. Dashboard: queue oldest-job age and runs in flight.
2. Find runs whose lease expired without progress: `status = running AND lease_until < now()`.
3. Check traces for the last completed step.
4. Expired leases are reclaimed automatically. If a run keeps failing at the same step, it is dead-lettered. Inspect, fix, then requeue with the same `run_id` (idempotent).

### Model quota exhausted
1. Confirm in gateway metrics (429 by model alias).
2. Ask the AI platform team for temporary headroom or a route to another region or deployment.
3. Reduce worker concurrency to match. Admission control turns new work away with `Retry-After` instead of letting it time out.
4. If quality allows, switch low-risk agents (Planner) to a cheaper alias by gateway configuration.

### Gateway outage
1. The circuit breaker opens; runs fail fast with a clear status (REL-5).
2. Queued runs wait; nothing is lost. Communicate expected recovery to channel owners.
3. On recovery, the breaker half-opens; watch for a 429 storm.

### Bad release
1. Stop the canary; route all traffic to the previous version.
2. Roll back image and configuration (previous Helm revision).
3. Find affected briefings by `service.version` and `app.prompt_version`. Mark them for review if quality was affected.
4. Add the failure to the golden set before re-releasing.

### Database restore
1. Restore from the latest backup within RPO (REL-7).
2. Runs accepted after the restore point but missing from the database: reconcile from the API access log and queue, and resubmit with the original `Idempotency-Key`.
3. Verify with the restore drill checklist.

---

## 6. On-call readiness

- [ ] SLOs and burn-rate alerts live ([OBSERVABILITY.md](OBSERVABILITY.md) §7)
- [ ] Dashboards linked from every alert
- [ ] Runbook entries above tested in stage
- [ ] Escalation paths to the gateway, identity, database and search teams agreed
- [ ] Restore drill done (REL-7)
- [ ] Rollback drill done (OPS-3)
