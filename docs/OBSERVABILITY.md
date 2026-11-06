# Observability

How we see what the service is doing: whether it is up and fast, whether the agents behave, what it costs, and whether answers are still good. It implements OBS-1 to OBS-4 in [NFR.md](NFR.md) and [ADR 0011](adr/0011-tracing-opentelemetry-langfuse.md). Volumes come from [CAPACITY.md](CAPACITY.md).

---

## 1. Four kinds of signal

| Signal | Answers | Kept |
|---|---|---|
| **Metrics** | Is the service healthy overall? Alert on these | 100%, aggregated |
| **Traces** | Where did *this* run spend its time, and where did it fail? | Tail-sampled (§4) |
| **Logs** | What exactly happened at this moment? | Structured JSON, IDs only, `trace_id` on every line |
| **Evaluations** | Is answer quality drifting, even though nothing errors? | Deterministic checks on every run; judge scores on a sample |

The **run record** (Postgres summary + object-storage artifact) is the audit source of truth, separate from all four. Tracing can be sampled, migrated or lost without losing audit.

---

## 2. Tracing

### Shape of one run

```
POST /v1/runs                                   api      (FastAPI auto-instrumentation)
└─ research_run                                 worker   continues the trace from the job row
   ├─ step.plan
   │  └─ invoke_agent planner
   │     └─ chat planner-default                gen_ai.* attributes; one span per attempt
   ├─ step.research [sq1..sq4]                  parallel after A7
   │  ├─ search                                 opensearch client span
   │  ├─ invoke_agent researcher
   │  │  └─ chat researcher-default
   │  └─ policy.trust_boundary                  app.claims.accepted / rejected
   ├─ policy.sufficiency                        app.coverage.*
   ├─ step.synthesise
   ├─ step.verify
   ├─ step.revise                               at most once
   ├─ step.verify
   └─ policy.confidence
```

### Instrumentation
- **Auto:** FastAPI, HTTP client (gateway calls), Postgres driver, OpenSearch client.
- **Agents and model calls:** Pydantic AI's built-in OpenTelemetry instrumentation (`Agent.instrument_all()`), which emits the OpenTelemetry GenAI semantic conventions.
- **Workflow steps and policies:** manual spans in the workflow, with domain attributes.
- **Resource attributes:** `service.name` (`research-api`, `research-worker`), `service.version` (image tag), `deployment.environment.name`, pod and node names.

### Attributes

| Attribute | Example | Notes |
|---|---|---|
| `gen_ai.operation.name` | `chat`, `invoke_agent` | GenAI conventions are still at "development" stability; pin the semconv version |
| `gen_ai.agent.name` | `verifier` | |
| `gen_ai.request.model` | `verifier-default` | The alias we asked for |
| `gen_ai.response.model` | actual model | Differs from the request when the gateway fell back (ADR 0010) |
| `gen_ai.usage.input_tokens` / `output_tokens` | `4120` / `610` | From the provider's usage field |
| `gen_ai.response.finish_reasons` | `["length"]` | `length` means truncated output and a validation retry |
| `app.run_id` | `r_01J…` | On spans and logs, **never on metric labels** |
| `app.prompt_version` | `verifier@7` | Ties behaviour to a prompt release |
| `app.claims.accepted` / `rejected` | `7` / `2` | Per research step |
| `app.rejection_reasons` | `["quote_not_found"]` | |
| `app.coverage` | `covered` / `thin` / `gap` | Per sub-question |
| `app.fallback_used` | `true` | |
| `app.run.status` | `degraded` | On the root span; drives tail sampling |

Prompts, completions, question text and document text are **not** recorded by default (DATA-5). They can be enabled per environment, only on a backend approved for that data, with PII masked first and retention no longer than the run record's.

### Context propagation

| Boundary | Mechanism |
|---|---|
| Caller → API | W3C `traceparent` header; the API returns the `trace_id` in a response header |
| API → queue → worker | The API stores the `traceparent` on the job row; the worker extracts it before starting `research_run`. A retried job uses a **span link** to the original trace |
| Worker → gateway | `traceparent` on every gateway request, so gateway spans join the run's trace |
| Parallel researchers | Each task starts from the parent step's context. `asyncio.create_task` and `asyncio.to_thread` copy context; a raw `ThreadPoolExecutor` or `run_in_executor` does not, so wrap with `contextvars.copy_context().run` |

```python
# API: put the trace context on the job
carrier: dict[str, str] = {}
propagate.inject(carrier)
await jobs.enqueue(run_id, payload, trace_carrier=carrier)

# Worker: continue it
ctx = propagate.extract(job.trace_carrier)
with tracer.start_as_current_span("research_run", context=ctx) as span:
    span.set_attribute("app.run_id", job.run_id)
```

### Pipeline
SDK (`BatchSpanProcessor`) → OTLP → **OpenTelemetry Collector** (redaction, tail sampling, attribute enrichment) → Langfuse for LLM views and cost, and the organisation's APM for latency and errors. Changing a backend is a Collector configuration change. Workers flush the span processor in their graceful-shutdown handler.

---

## 3. Metrics

Labels are bounded: `agent`, `model` (alias), `status`, `reason`, `environment`, `channel`. Run, user and customer IDs, and question text, belong on spans, not on labels.

### Service (RED and USE)

| Metric | Type | Labels |
|---|---|---|
| `http_server_request_duration_seconds` | histogram | route, status_code |
| `runs_total` | counter | status (`completed`, `degraded`, `insufficient_evidence`, `failed`, `cancelled`) |
| `run_duration_seconds` | histogram | status |
| `queue_depth` | gauge | priority |
| `queue_oldest_job_age_seconds` | gauge | priority |
| `worker_runs_in_flight` | gauge | — |
| `admission_rejected_total` | counter | reason (`rate_limit`, `queue_full`) |

### Agent behaviour and cost

| Metric | Type | Labels | What it tells you |
|---|---|---|---|
| `gen_ai.client.token.usage` | histogram | agent, model, token type | Token spend per agent |
| `gen_ai.client.operation.duration` | histogram | agent, model | Model latency per alias |
| `run_cost` | histogram | channel | Cost per run; a long tail means oversized inputs or retries |
| `llm_fallback_total` | counter | agent, from_model, to_model | Silent quality risk, especially on the Verifier |
| `llm_validation_retries_total` | counter | agent, model | Rises after a model change: contract and prompt mismatch |
| `gateway_responses_total` | counter | model, code | 429 and 5xx before they become an outage |
| `trust_boundary_rejections_total` | counter | reason | Measured hallucination rate |
| `findings_unverified_ratio` | histogram | — | Verifier failing or bypassed |
| `review_required_total` | counter | reason | Load on human reviewers |
| `coverage_gap_ratio` | histogram | — | The corpus doesn't cover what people ask: a content signal |
| `result_cache_hits_total` / `misses_total` | counter | — | Token savings from the cache |

Histograms carry **exemplars** (trace IDs), so a latency spike links straight to example traces.

---

## 4. Sampling at volume

At the 4M-runs-a-day ceiling a run produces ~30 spans, so 120M spans a day. Tail sampling in the Collector keeps:

| Runs | Kept |
|---|---|
| `failed`, `degraded`, `insufficient_evidence` | 100% |
| Any fallback model, any validation retry | 100% |
| Slower than the p95 target | 100% |
| Sampled for online evaluation | 100% (the evaluation needs the trace) |
| Everything else | 2% (tunable) |

Totals and rates always come from metrics. Tail sampling needs all spans of a trace on the same Collector instance: use a load-balancing exporter keyed by `trace_id` in front of the sampling tier.

---

## 5. Logs

- JSON to stdout, one object per line: `timestamp`, `level`, `service`, `run_id`, `trace_id`, `span_id`, `event`, plus IDs relevant to the event.
- No question text, document text, prompts or completions (DATA-5); log the IDs that lead to them.
- Span events explain a span (retry, fallback, validation error). Logs are for operational events (worker started, job claimed, shutdown).

---

## 6. Answer quality in production

| Check | Runs on | Cost |
|---|---|---|
| Deterministic: no invented quotes, recorded disagreements surfaced, every finding has a verdict, gaps reported | Every run, as span attributes and metrics | Free |
| LLM-as-judge: faithfulness to quotes, relevance to the question | 1–5% sample, scored in Langfuse against the trace | One extra model call per sampled run |
| User feedback (useful / wrong, with reason) | When given, linked by `trace_id` | Free; best source of new golden-set cases |
| Golden set against production configuration | Nightly | Small, fixed |

**Drift to watch:**
- **Input drift:** new topics the corpus doesn't cover, seen in the gap ratio and the insufficient-evidence rate.
- **Model drift:** a provider changes a model behind an alias, seen in rejection, retry and judge scores moving together. Pin model versions at the gateway.

---

## 7. SLOs and alerts

| SLI | SLO | Error budget (30 days) |
|---|---|---|
| API submit requests that succeed (non-5xx) | 99.9% | 43 min |
| Accepted runs that reach a final status within 3 min | 99% | 1% of runs |
| Nightly golden-set deterministic checks | 100% | none: any failure blocks releases |
| Nightly golden-set judge score | ≥ committed baseline − tolerance | 2 consecutive misses |

Alerts use **multi-window burn rates**: page at fast burn (about 14× over 1 h and 5 min); ticket at slow burn (about 1× over 3 days).

| Severity | Condition |
|---|---|
| Page | Run-failure SLO fast burn · queue oldest job > 5 min · gateway circuit open · admission rejections > 5% for 10 min |
| Ticket | Fallback rate > 10% for 1 h · validation retries 2× week on week · trust-boundary rejections 2× baseline · cost at 80% of monthly budget · nightly eval below baseline |
| Dashboard | Tokens per agent, cache hit rate, coverage gaps, review-required volume |

---

## 8. Dashboards

1. **Service:** submit rate and latency, run outcomes, run duration percentiles, queue depth and age, admission rejections.
2. **Models and cost:** tokens and cost per agent and model, gateway 429/5xx, fallback rate, cache hit rate, spend against budget.
3. **Quality:** trust-boundary rejections by reason, unverified ratio, review-required, judge scores, user feedback, gap ratio.
4. **Per run:** search by `run_id` or `trace_id` → trace → run record.

---

## 9. Common mistakes

| Mistake | Symptom | Prevention |
|---|---|---|
| Trace context not stored on the job | Worker traces have no parent | `traceparent` column on the job; integration test asserts one trace per run |
| IDs as metric labels | Metric store memory and cost explode | Label allowlist reviewed in code review |
| Prompts in spans by default | Customer data in a third-party tool | Off by default; Collector redaction processor |
| Tokens and cost counted by both app and gateway | Double cost on dashboards | Gateway is the cost source of truth; spans joined by `traceparent` |
| Static price table | Cost wrong after a price change | Cost from the gateway, or a versioned price table with effective dates |
| Head sampling | The failed run you need was dropped | Tail sampling |
| No flush on shutdown | Last runs before a deploy have no trace | Flush in the shutdown handler |
