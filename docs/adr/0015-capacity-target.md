# 0015. Capacity target: 2–4 million customers a day

- **Status:** Proposed
- **Date:** 2026-11-06
- **Related:** CAP-1, CAP-2, CAP-5, REL-1, COST-4, DATA-2, OBS-1; ADR 0002, 0009, 0011; [CAPACITY.md](../CAPACITY.md)

## Context
The first NFRs sized the service as an internal analyst tool (500 runs a day, 20 concurrent). The service now has to serve 2–4 million customers a day and go live in 8 weeks. At the 4 million runs-a-day ceiling, that means ~139 runs/s at peak, ~8,300 runs in flight and ~167M model tokens per minute ([CAPACITY.md](../CAPACITY.md)).

## Decision
- Design for **4 million runs a day** at a 3× peak; provision for measured demand.
- **Model throughput is the primary capacity:** reserved throughput across several regions and deployments behind the gateway, requested in week 1.
- **Token spend is a design concern:** model tiering per agent chosen by evaluation, provider prompt caching, and an entitlement-aware result cache.
- **Admission control:** per-customer and per-channel rate limits and priority classes ahead of the queue.
- **Availability 99.9%**, with multi-zone stateful dependencies.
- **Storage split:** run summaries in day-partitioned Postgres tables; full artifacts in object storage with lifecycle rules.
- **Tail-sampled tracing;** metrics carry totals; run records stay complete.
- **ADR 0009 (Postgres queue) is kept, with a trigger:** if the stage load test at peak shows queue or checkpoint writes taking Postgres past 60% of its capacity, the queue moves to the organisation's message broker and Postgres keeps only checkpoints and run records.

## Alternatives considered
| Option | Why not |
|---|---|
| Provision for the ceiling from day one | Pays for idle model throughput; the ceiling assumes every customer asks |
| Synchronous API | 60 s requests at 139/s hold ~8,300 open connections through every proxy; no back-pressure |
| Move to Kafka now | Adds a dependency before a load test shows the need; the trigger above decides |

## Consequences
- NFR targets for capacity, availability, cost, retention and tracing change (this ADR's related IDs).
- The launch critical path runs through other teams: gateway capacity, identity onboarding, security review.
- The per-run planning figures must be replaced by stage measurements before the production capacity request is final.
