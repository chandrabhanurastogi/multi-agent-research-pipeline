# 0009. Postgres-backed job queue for the worker

- **Status:** Accepted
- **Date:** 2026-10-15
- **Related:** CAP-4, REL-2, REL-4; ADR 0003; plan step A2

## Context
A run takes minutes, so the API accepts it and a separate worker executes it. Jobs must survive restarts, run once even if delivered twice, and back off when the gateway quota is exhausted. Postgres is already required (run records, LangGraph checkpoints).

## Decision
Use a **Postgres-backed queue**, with **procrastinate** (Python, Postgres-based, async, retries, job locks) as the first candidate:
- A job is "execute run `<run_id>`"; the run ID is the deduplication key, so a duplicate job is a no-op.
- The job only drives the LangGraph run; progress lives in LangGraph checkpoints, so a retried job resumes rather than restarts (REL-3).
- Worker concurrency is configuration, sized to the gateway quota.
- To verify in A2 with the pinned version: recovery of jobs whose worker died (stalled-job detection). If it is not adequate, fall back to a small own queue table using `SELECT ... FOR UPDATE SKIP LOCKED` with a lease timeout.

## Alternatives considered
| Option | Why not |
|---|---|
| Celery + Redis/RabbitMQ | Another stateful component to run and secure; Celery's model is a poor fit for async LangGraph |
| Kafka / RabbitMQ | Right choice **if the organisation already runs one for Java services**; otherwise heavy for this volume (CAP-2) |
| Temporal | Strong, but a cluster to operate; overlaps with LangGraph checkpointing |
| LangGraph Platform | Includes a queue, but a commercial server; ADR 0003 keeps to the open-source library |
| In-process background tasks | Lost on restart (violates REL-2) |

## Consequences
- One fewer infrastructure dependency; queue and data share backups.
- Postgres load grows with polling; fine at CAP-2 volumes, revisit above that.
