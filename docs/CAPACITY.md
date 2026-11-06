# Capacity and Scale

How big this service has to be, worked out from the target load, and what that changes in the design. The numbers drive [NFR.md](NFR.md) (CAP, COST, DATA, OBS), [ADR 0015](adr/0015-capacity-target.md) and the launch plan in [PRODUCTION_PLAN.md](PRODUCTION_PLAN.md).

**Status: proposed.** The per-run figures come from the v0.1.0 baseline and are replaced by measurements from the stage load test (A5, Phase C). Prices are placeholders for the gateway contract rates.

---

## 1. Target

- **2–4 million customers a day** reach the service through the organisation's customer channels and internal tools.
- **Production in 8 weeks** (see the launch plan).
- **Design ceiling: 4 million runs a day**, as if every customer requested one briefing. The architecture must hold this; capacity (pods, gateway throughput) is provisioned for measured demand and grows towards it.

What share of customers request a briefing is a product question to confirm. The table shows three scenarios so that the answer changes the provisioning, not the design.

## 2. Planning figures per run

| Figure | Value | Source |
|---|---|---|
| LLM calls | 7 (Planner, 4 Researchers, Synthesiser, Verifier; a revision adds 2) | v0.1.0 run traces |
| Tokens | 20k in + out | Baseline 5–10k on short sample documents, doubled for real document lengths |
| Duration | 60 s p50 | Baseline ~20 s model time; real documents, queueing and retries added |
| Searches | 4 (one per sub-question) | Workflow |
| Trace spans | ~30 | One per step, LLM call, search and policy |
| Run summary row (Postgres) | ~2 KB | Status, IDs, models, prompt versions, scores |
| Full run artifact (object storage) | ~100 KB | `run.json` + `briefing.md` |
| Peak-to-average ratio | 3× | Demand concentrated in daytime hours across served regions |

## 3. What the load means

Little's law: runs in flight = arrival rate × duration.

| | A: 0.5M runs/day | B: 2M runs/day | C: 4M runs/day (ceiling) |
|---|---|---|---|
| Average arrival | 5.8 runs/s | 23 runs/s | 46 runs/s |
| **Peak arrival** | 17 runs/s | 69 runs/s | **139 runs/s** |
| Runs in flight at peak | ~1,000 | ~4,200 | **~8,300** |
| LLM calls at peak | 122/s (7.3k RPM) | 486/s (29k RPM) | **972/s (58k RPM)** |
| Tokens per minute at peak | 21M | 83M | **167M** |
| Tokens per day | 10B | 40B | 80B |
| Searches at peak | 69 qps | 278 qps | 556 qps |
| Spans per day | 15M | 60M | 120M |
| Run summaries per day (Postgres) | 1 GB | 4 GB | 8 GB |
| Run artifacts per day (object storage) | 50 GB | 200 GB | 400 GB |
| Worker processes at peak (50 runs each) | ~21 | ~85 | ~170 |

### Cost per run

`cost per run = tokens per run × blended price per token`. At 20k tokens:

| Blended price (placeholder) | Per run | Per day at B | Per day at C |
|---|---|---|---|
| $0.40 per 1M tokens | $0.008 | $16k | $32k |
| $2.00 per 1M tokens | $0.04 | $80k | $160k |

At this volume, model choice per agent and caching move the cost by six figures a month, so both are design work, not later optimisation.

---

## 4. Consequences for the design

### LLM throughput is the binding constraint
Pods are cheap to add. Model throughput is not: 167M tokens per minute at peak is far above default provider quotas.
- Agree **reserved or provisioned throughput** with the AI platform team in week 1. It has the longest lead time of anything in the plan.
- The gateway routes across **several deployments and regions** of each approved model, so one deployment's limit or outage doesn't throttle the service.
- Worker concurrency is sized to the gateway allocation, not to CPU. The HPA scales on queue depth, capped by quota.

### Fewer tokens per run
- **Model tiering per agent:** the Planner and Researchers on a small fast model, the Verifier on the strongest approved model. Decided by evaluation (A6), not by guesswork.
- **Provider prompt caching:** agent instructions are a fixed prefix; put variable content last.
- **Result cache:** key = normalised question + corpus version + entitlement-set hash + prompt and model versions. The entitlement hash means a cached briefing is never served to someone with different document access. Each 10% hit rate saves 10% of token spend.
- **Retrieval cache** for popular sub-questions within a corpus version.

### Admission control and fairness
- **Per-customer and per-channel rate limits** at the API gateway, so one client or bot cannot consume the shared model allocation.
- **Priority classes:** interactive requests ahead of batch or scheduled ones.
- When the queue is full, return `429` with `Retry-After` (CAP-4). Never accept work the service cannot finish within LAT-3.

### Queue and checkpoints
- Enqueue at 139/s is within reach of a Postgres `SKIP LOCKED` queue. **Checkpoint writes** are heavier: about 10 per run gives ~1,400 writes/s at peak. Keep checkpoint payloads small (references to object storage, not documents), prune checkpoints when a run finishes, and partition the job table by day.
- ADR 0009 is re-validated by the stage load test at peak C. If Postgres cannot hold it with headroom, the queue moves to the organisation's broker (Kafka or SQS / RabbitMQ) and Postgres keeps checkpoints only. [ADR 0015](adr/0015-capacity-target.md) records this trigger.

### Storage and retention
- At ~3 TB a year, run summaries live in Postgres, **partitioned by day**, with old partitions dropped at the end of retention (DATA-2).
- Full artifacts (~146 TB a year at C) live in object storage with lifecycle rules: 90 days hot, then delete or archive as agreed with compliance.

### Results delivery
- 8,300 runs in flight, each polled every 2 s, is ~4k GET/s for nothing. Offer **server-sent events or webhooks** to calling channels; keep polling with a server-suggested interval.

### Observability volume
- 120M spans a day is too many to keep at full detail. **Tail sampling** in the Collector keeps 100% of failed, degraded, slow and fallback runs and a small share of healthy ones. Totals come from metrics, never from counting traces. The run record stays 100% for audit. See [OBSERVABILITY.md](OBSERVABILITY.md).

### Search
- 556 qps at peak is moderate for OpenSearch with replicas. The entitlement filter must stay inside the query (SEC-3), so cache keys include the entitlement set.

### Availability
- A customer-facing service at this scale needs **99.9%**, multi-zone for every stateful dependency and at least two model regions behind the gateway. A regional model outage then reduces throughput instead of stopping it.

---

## 5. Verify before launch

| Check | How | Pass |
|---|---|---|
| Sustained load at peak B for 1 h | Stage, gateway stub with realistic latency and 429s | SLOs met, no lost runs |
| Burst to peak C for 15 min | Same | Back-pressure works: `429`s, no timeouts, queue drains |
| Real model run at 5% of peak B | Stage against the real gateway | Measured tokens, latency and cost replace the planning figures |
| Worker kill at peak | Chaos test | Runs resume, no repeated LLM calls (REL-3) |
| Gateway region failure | Fault injection | Throughput drops, error rate stays within budget |
