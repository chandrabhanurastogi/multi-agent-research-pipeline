# 0002. LLMs reached only through an enterprise gateway

- **Status:** Accepted
- **Date:** 2026-10-14
- **Related:** SEC-4, OPS-2, COST-1, DATA-3; ADR 0010

## Context
The take-home calls Gemini directly with a key in `.env`. In an enterprise, provider keys are high-value secrets, quotas and costs are shared across teams, and only approved models may be used.

## Decision
The service calls an **enterprise LLM gateway** (OpenAI-compatible API) and never holds provider credentials.
- **Provider credentials** belong to the AI platform team, inside the gateway; ideally none are static (managed identity, IAM role, service account).
- **Our credential** identifies the service to the gateway: a scoped virtual key or OAuth2 client credentials in Vault, or none with workload identity. It is obtained in one function, so the method can change without touching agents.
- Agents ask for **model aliases** (`planner-default`, `verifier-default`); the gateway maps aliases to real models.
- Locally, a LiteLLM proxy container plays the gateway; the Gemini key lives only in its configuration.

## Alternatives considered
| Option | Why not |
|---|---|
| Provider key in Vault, called directly | A leaked key exposes the whole provider account; no central quota, cost attribution or model approval |
| Gateway deployed in our Helm chart | The gateway is a shared platform service owned by another team, not part of our release |

## Consequences
- Switching provider or model is a gateway configuration change.
- We depend on the gateway's availability and quota: circuit breaker and back-pressure required (REL-5, CAP-4).
- We must record which real model answered each step, from the gateway's response.
