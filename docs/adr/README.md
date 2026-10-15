# Architecture Decision Records

One file per significant decision: the context, what we decided, what we rejected and what follows from it. An accepted ADR is not edited; a changed decision gets a new ADR that supersedes it.

**Status values:** `Proposed` (recommendation, awaiting agreement) · `Accepted` · `Superseded by NNNN`.

| ADR | Decision | Status | Needed by |
|---|---|---|---|
| [0001](0001-same-repo-main-is-production.md) | Same repo; `main` is the production line; take-home frozen on a tag | Accepted | — |
| [0002](0002-llm-access-through-enterprise-gateway.md) | LLMs reached only through an enterprise gateway; no provider keys in this service | Accepted | — |
| [0003](0003-pydantic-ai-agents-langgraph-orchestration.md) | Pydantic AI inside agents, LangGraph for orchestration | Accepted | — |
| [0004](0004-local-first-same-technology-config-only.md) | Build locally on production technologies; environments differ only by configuration | Accepted | — |
| [0005](0005-generic-cicd-templates.md) | Generic Jenkins / Helm / Vault templates, adapted to organisation conventions later | Accepted | — |
| [0006](0006-uv-for-dependencies.md) | uv for dependency management and lock file | Accepted | A1 |
| [0007](0007-settings-from-environment.md) | One validated settings object, read from environment variables only | Accepted | A1 |
| [0008](0008-oidc-authentication-keycloak-locally.md) | OIDC authentication; Keycloak locally | Accepted | A2 |
| [0009](0009-postgres-backed-job-queue.md) | Postgres-backed job queue for the worker | Accepted | A2 |
| [0010](0010-model-fallback-in-gateway.md) | Model fallback chain configured in the gateway | Proposed | A4 |
| [0011](0011-tracing-opentelemetry-langfuse.md) | OpenTelemetry tracing, Langfuse as LLM observability backend | Proposed | A5 |
| [0012](0012-evaluation-framework.md) | Evaluation: own deterministic checks plus DeepEval, run by pytest | Proposed | A6 |
| [0013](0013-guardrails.md) | Guardrails at the gateway where offered, Presidio for PII in the app | Proposed (decide at A9) | A9 |
| [0014](0014-embeddings-and-reranker.md) | Embedding model and reranker chosen by evaluation on the golden set | Proposed (decide at A8) | A8 |

## Template

```markdown
# NNNN. Title

- **Status:** Proposed | Accepted | Superseded by NNNN
- **Date:** YYYY-MM-DD
- **Related:** NFR IDs, other ADRs

## Context
What forces this decision; what is true today.

## Decision
What we will do, in one or two sentences, then the details.

## Alternatives considered
| Option | Why not |
|---|---|

## Consequences
What becomes easier, what becomes harder, what we must now do.
```
