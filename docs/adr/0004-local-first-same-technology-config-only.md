# 0004. Build locally on production technologies; environments differ only by configuration

- **Status:** Accepted
- **Date:** 2026-10-15
- **Related:** OPS-1; plan phases A, B, C

## Context
We want to make the application production-ready before infrastructure exists, without a painful integration at the end.

## Decision
- **Phase A** builds the application locally with `docker compose`, using the **same technologies** as production: Postgres, S3-compatible storage (MinIO), OpenSearch, an LLM gateway (LiteLLM), Langfuse, an OIDC provider (Keycloak).
- **Phase B** builds infrastructure with a trivial image. **Phase C** connects them by configuration only.
- Between environments only configuration differs: endpoints, credentials, model pins, thresholds, replica counts, flags. Never code paths, the image, the schema or dependencies.
- The application runs as an OpenShift-like container from the start: non-root arbitrary UID, read-only root filesystem, health probes, JSON logs to stdout.

## Alternatives considered
| Option | Why not |
|---|---|
| Lighter local substitutes (SQLite, local folders, direct Gemini) | Phase C becomes a rewrite: different SQL, concurrency, auth and failure modes |
| Infrastructure first | Infrastructure designed without knowing what the application needs |
| Deploy a skeleton to dev first, then grow | Needs infrastructure before any application work; chosen order lets work proceed without other teams |

## Consequences
- The local stack is heavier (several containers) but faithful.
- If Phase C needs a code change, that is a Phase A defect to fix and record.
