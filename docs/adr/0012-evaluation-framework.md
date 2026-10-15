# 0012. Evaluation: deterministic checks plus DeepEval, run by pytest

- **Status:** Proposed
- **Date:** 2026-10-15
- **Related:** QUAL-1 … QUAL-5, SEC-8; plan step A6

## Context
The 85 offline tests prove behaviour with a fake LLM, not answer quality. Every change to prompts, models, search or orchestration must be scored against a baseline before release.

## Decision
- **Golden set** versioned in `eval/`: questions with expected findings, disagreements, gaps and injection cases (starting from the corpus traps).
- **Deterministic checks first** (exact, cheap, no judge needed): no invented quotes, expected gaps reported, disagreements reported, injection ignored.
- **LLM-as-judge metrics with DeepEval** (pytest-native, Python) for what code cannot check: faithfulness to sources, answer relevance, completeness against expected findings. The judge uses a different model family from the Synthesiser, through the gateway.
- `make eval` runs everything and writes a report; the scores of the current pipeline are committed as the **baseline**. CI fails when a metric drops below baseline minus a tolerance agreed in A6.

## Alternatives considered
| Option | Why not |
|---|---|
| Ragas | Strong RAG metrics; can be added for retrieval metrics in A8 |
| promptfoo | Good for prompt comparison; Node/YAML tooling outside our Python test stack |
| LLM-as-judge only | Judges are noisy; the most important properties are checkable exactly |

## Consequences
- Each eval run costs real model calls; small set in sit, full set in stage.
- The golden set needs analyst input to grow beyond the mock corpus.
