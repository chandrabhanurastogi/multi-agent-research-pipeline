# 0010. Model fallback chain configured in the gateway

- **Status:** Proposed
- **Date:** 2026-10-15
- **Related:** REL-5, OPS-2; ADR 0002; plan step A4

## Context
Today the app holds a fallback chain (`LLM_FALLBACK_MODEL`) and records which model answered each step. With a gateway (ADR 0002), the gateway can also retry and fall back across models.

## Decision
- Configure fallback **in the gateway**, per model alias (e.g. `verifier-default`: model X, then model Y). The app asks for an alias.
- The app still **records the model that actually answered**, taken from the gateway's response, and keeps the policy: in `stage`/`prod`, a briefing whose Synthesiser or Verifier ran on a fallback is not published without review (setting, default on).
- The app keeps only transport-level retries for gateway errors (timeouts, 5xx), with backoff and a circuit breaker.
- To verify in A4: the gateway reports the answering model reliably. If not, keep the fallback chain in the app (as today) and use gateway aliases without fallback.

## Alternatives considered
| Option | Why not |
|---|---|
| Fallback in the app (today) | Duplicates gateway logic; model changes need an app release |
| No fallback | Single model outage stops all runs |

## Consequences
- Changing the fallback order is a gateway configuration change.
- We depend on the gateway exposing the answering model.
