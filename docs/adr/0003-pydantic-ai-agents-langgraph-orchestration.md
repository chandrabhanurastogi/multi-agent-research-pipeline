# 0003. Pydantic AI inside agents, LangGraph for orchestration

- **Status:** Accepted
- **Date:** 2026-10-14
- **Related:** REL-2, REL-3, QUAL-1; plan steps A4, A7

## Context
Two problems at two levels:
- **Inside one LLM call:** the output must be a valid typed object (claims with quotes and source IDs, verdicts), or the deterministic policies cannot work.
- **Between calls:** production runs must survive crashes, pause for analyst approval of the plan, resume, run researchers in parallel and support follow-up questions.

## Decision
- **Pydantic AI** for every agent: typed output contracts, one retry with the validation error, provider portability, `FunctionModel`/`TestModel` for offline tests. Only `agents/` imports it.
- **LangGraph** for the workflow: each step a node, Postgres checkpointer, `interrupt()` for plan approval, conditional edges for the bounded revision loop and the insufficient-evidence stop, threads for session memory.
- Open-source LangGraph library only; no dependency on the commercial LangGraph Platform server.

## Alternatives considered
| Option | Why not |
|---|---|
| Plain Python orchestration (take-home) | No checkpoint, resume or human approval without writing that machinery ourselves |
| LangChain/LangGraph for both layers | Structured output through LangChain's model layer; validation retry less direct; fine if the organisation standardises on it |
| `pydantic-graph` for orchestration | Less mature persistence and human-in-the-loop support |
| Temporal | Strong durable execution, but a separate cluster to run; preferred if the organisation already operates Temporal |

## Consequences
- The migration in A7 turns existing step functions into nodes; agents do not change.
- Two frameworks to keep up to date; the boundary (agents vs workflow) must stay clean.
