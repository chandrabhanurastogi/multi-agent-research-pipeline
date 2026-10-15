# 0011. OpenTelemetry tracing, Langfuse for LLM observability

- **Status:** Proposed
- **Date:** 2026-10-15
- **Related:** OBS-1, OBS-2, COST-1; plan step A5

## Context
Today each run's trace is a list in `run.json`. Production needs traces across API, queue, worker and LLM calls, plus cost and quality metrics, in a shared tool.

## Decision
- Instrument with **OpenTelemetry** (vendor-neutral): FastAPI, database and HTTP clients, plus Pydantic AI's built-in OpenTelemetry instrumentation for agent and model spans; LangGraph nodes as spans.
- Export through an **OpenTelemetry Collector** to **Langfuse** (self-hostable, accepts OTLP, shows prompts, tokens and cost per span).
- The run record keeps its own per-step summary (status, model, tokens) for audit, independent of the tracing backend.
- Prompt and document text in spans is configurable; off by default in prod unless the platform is approved for that data (DATA-5).

## Alternatives considered
| Option | Why not |
|---|---|
| LangSmith | SaaS-first, closest to the LangChain ecosystem; fine if the organisation already uses it |
| Arize Phoenix, Logfire | Viable; Langfuse chosen for self-hosting and cost tracking |
| Only the organisation's APM (Dynatrace, Datadog, ...) | Good for latency and errors, weak for prompts, tokens and LLM cost; the collector can export to both |

## Consequences
- Local stack gains Langfuse and a collector.
- Switching backend is a collector configuration change.
