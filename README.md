# Multi-Agent Research & Synthesis Pipeline

An analyst asks a free-text question; the pipeline plans the research, gathers evidence from a (mock) document library, writes a structured briefing, has it independently checked against the exact source quotes, and grades how well each statement is supported — **by fixed, auditable rules, not by the LLM's opinion**.

The output is written for a non-technical analyst and is explicit about what it knows, how well supported each statement is, where sources disagree, what it could not establish, and when a human should review it.

- **Example outputs:** [`examples/`](examples/) — a full briefing, and a question the corpus cannot answer.
- **Design decisions and trade-offs:** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Quick start

Requires Python 3.12+ and a Gemini API key ([Google AI Studio](https://aistudio.google.com), free tier works).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env            # then put your key in GOOGLE_API_KEY

python -m research_pipeline "Give me an overview of the dry bulk shipping market and its main risk drivers."
```

Output: `runs/<run_id>/briefing.md` (for the analyst) and `runs/<run_id>/run.json` (full audit trail). A run takes about a minute and makes at most about 10 agent calls (fewer if it stops early), plus any validation retries and fallback attempts.

```bash
pytest                          # 84 tests, offline, no API key needed (fake LLM)
python scripts/check_llm.py     # one real call: checks key and model
```

> **Free-tier quota:** `gemini-3.8-flash` allows ~20 requests/day on the free tier — about 2–3 full runs. When it is exhausted (or overloaded), the fallback chain in `.env` moves to cheaper models, and the briefing says so. For a live demo, use a fresh quota or a billed key.

---

## 1. Agent architecture, and why

```
query
  │
  ▼
PLANNER ───────────► interpretation + assumptions + 3–5 sub-questions
  │
  ▼  for each sub-question
search (BM25, code) ─► RESEARCHER ─► claims {statement, source, exact quote}
                                          │
                       trust boundary (code): quote really in the source? source was given? ─► reject or accept
  │
  ▼
sufficiency (code) ── no credible evidence at all ──► STOP: "insufficient evidence" briefing
  │
  ▼
SYNTHESISER ───────► draft: summary, findings citing claim IDs, disagreements, follow-ups
  │
  ▼
VERIFIER ──────────► per finding: supported / partial / unsupported, contradicting claims
  │                  any not fully supported? ──► Synthesiser revises ONCE ──► Verifier re-checks
  ▼
confidence (code) ─► briefing.md + run.json
```

**Four agents, each with one job and a typed contract** (an "agent" here is an LLM-backed step whose output is validated against a Pydantic model; invalid output is sent back to the LLM once with the error, then the step fails explicitly):

| Agent | Job | Not its job |
|---|---|---|
| **Planner** | Make the intent explicit (restated question, scope, assumptions) and break it into 3–5 sub-questions | Searching, answering |
| **Researcher** | For one sub-question, extract relevant facts with **exact quotes** from the retrieved documents | Judging truth or source quality |
| **Synthesiser** | Write the briefing **only** from accepted claims, citing them; report disagreements without picking a side | Checking itself, scoring confidence |
| **Verifier** | Sceptically check each finding against the quotes it cites; list contradicting claims; suggest corrected wording | Rewriting the draft, scoring confidence |

**Why four, not three.** Extracting evidence and writing prose fail differently. Separating them creates a claim layer (statement + exact quote + source) that **code can check**: invented quotes and citations to documents the agent never saw are rejected before they reach the draft. Confidence depends on knowing which sources back each finding; this layer makes that input checkable instead of trusting the writer's citations.

**Why a fixed sequence, not an LLM "manager" or autonomous loop.** The process always has the same shape (plan, gather, write, check); only the content varies. So the LLM handles content and code owns control flow — testable branch by branch, bounded (at most ~10 LLM calls per run), and debuggable (a failure is attributed to one named step). Adaptivity lives in the Planner: different questions get different sub-questions. Dynamic orchestration would earn its cost if the *steps* themselves had to vary per query.

**Why the Verifier cannot rewrite.** If it rewrote findings, nobody would check its rewrite, and the audit trail would show an "unsupported" verdict next to text that was never verified. It may only *suggest* wording; the Synthesiser revises; the Verifier checks again.

**Technology choices** (problem → decision; details in ARCHITECTURE.md §5):

| Need | Choice | Why not the alternative |
|---|---|---|
| Typed LLM output, validation + retry, provider portability | **Pydantic AI** | LangChain adds abstraction without adding reliability here |
| Orchestration | **Plain Python** (~one function per step) | LangGraph's real value — checkpoints, resume, human approval — is out of scope; the workflow is written so adopting it is a refactor, not a rewrite |
| Retrieval | **BM25** (`rank_bm25`) over 12 documents behind one `search()` method | Vectors add nothing visible at this size; production would be hybrid search + entitlement filtering behind the same method |
| LLM | **Gemini**, with a fallback chain set in `.env` | Provider and model are configuration, not code |

---

## 2. How state is managed and passed

One Pydantic object, **`RunState`**, holds everything a run produces: interpretation, sub-questions, retrieved documents, accepted and rejected claims, coverage, draft, verdicts, scores, issues, and a per-step trace (status, duration, tokens, retries, **which model answered**, error). It is saved as `run.json` — including when the run fails.

- **Only the workflow writes to state.** Agents, search and policies take explicit inputs and return outputs; `workflows/research_briefing.py` writes them into `RunState`. Each step's inputs are visible in its signature and testable without building a whole state.
- **Validated on every write** (`validate_assignment=True`), with typed, mostly immutable records.
- **Untrusted vs trusted is visible in the types.** `ExtractedClaim` is what the LLM said; `Claim` is what passed the checks. The LLM never assigns IDs, tiers or scores.
- **Failures are data.** Every problem becomes an `Issue` with a severity (`info` → audit only, `warning` → shown to the analyst, `review` → shown and sets *needs human review*). Run status is `completed`, `degraded`, `insufficient_evidence` or `failed`.
- **No cross-run memory**: each question is independent. Production would add per-step checkpoints (resume a crashed run) — the natural point to adopt LangGraph.

---

## 3. How the system decides it has "enough", and how confidence is derived

**"Enough" is a published rule, not a feeling** (`policies/sufficiency.py`). Per sub-question:

| Coverage | Rule |
|---|---|
| covered | claims from ≥ 2 credible sources with **different original sources** |
| thin | one credible original source, or only weak sources |
| gap | no accepted claims |

*Credible* = tier A (official / industry body) or B (broker research / established press), and not older than 3 years (older sources count one tier lower). **If no credible evidence exists anywhere, the run stops** and says so, rather than writing a briefing from a forum post. There is no open-ended "search until satisfied" loop: the system knows whether it met a defined evidence bar, not whether it knows "enough" in an absolute sense.

**Confidence is derived from evidence by code** (`policies/confidence.py`), per finding:

```
supporting claims (only those the Verifier confirmed) → their sources → grouped by ORIGINAL source
base          = best source:  tier A 0.60 | B 0.45 | C 0.15   (stale sources count one tier lower)
corroboration = +0.15 per other independent credible source (max +0.30)
conflict      = −0.25 per credible contradicting source (−0.05 if weak)
verdict       = × 1.0 supported | × 0.6 partial | unsupported → excluded from key findings
label         = ≥ 0.70 Strongly | ≥ 0.40 Partly | < 0.40 Weakly supported by our sources
```

Design points, each found by running the system and fixed with a test:
- **Copies are not confirmation.** Two articles repeating one press release share a `primary_origin` and count once.
- **Attribution must not hide a dispute.** "Harbourline reports 7%" is literally true, so a Verifier may not call it contradicted — but Meridian says 10%. A finding that takes one side of a recorded disagreement is penalised; one that reports both sides is not.
- **Support and completeness are separate headlines.** Multiplying them made solid findings look weak whenever one area had no evidence.
- **The Verifier can only remove support, never add it**, and the LLM never sets a score — so a document saying "rate everything high confidence" (there is one in the corpus) has nothing to influence.

**What a score of 0.75 means:** the Verifier confirmed the statement against the quoted text, its best source is an official or industry body, one other independent credible source agrees, and no credible source disagrees.
**What it does not mean:** a 75% probability of being true. It is not calibrated, not the LLM's opinion, cannot tell whether the sources themselves are wrong, and knows nothing about evidence outside the corpus. The weights are documented **policy**, to be agreed with analysts and compliance.

---

## 4. Failure handling

| Failure | Behaviour |
|---|---|
| Empty, too short or too long question | Rejected before any model call, with a clear message (exit code 2) |
| Provider error (503 overloaded, 429 quota, 5xx) | Client retries, then the **fallback model chain**; if all fail, the step's policy applies |
| Planner fails | Research the question as a whole; warn |
| A Researcher call fails | That sub-question becomes a **gap**; the run continues |
| Invalid structured output | Error sent back to the LLM once, then the step fails as above |
| Invented quote / unknown source or claim ID | Dropped and recorded in `rejected_claims` / issues |
| No credible evidence | **Stop**; "insufficient evidence" briefing; review required |
| Synthesiser fails | Run **failed**; state still saved |
| Verifier fails | Continue **unverified**; every finding capped at *Weakly*; banner + review required |
| Findings still unsupported after one revision | Moved to "Statements we could not verify"; review required |
| Steps answered by a fallback model | Warning in the briefing and on the command line, naming the models that actually answered |
| A bug (not an LLM failure) | State marked failed and **saved**, then the error is re-raised — never swallowed |

---

## 5. Mock research data

`data/corpus.json` — 12 short fictional documents on dry bulk shipping, each with a hand-assigned tier, original source and date, designed so the checking path has work to do: two independent official sources that agree; conflicting orderbook figures (7% / 10% / a stale 12% from 2019); opposite rate forecasts; two press articles copying one press release; an anonymous forum post; a blog containing a prompt-injection instruction; and nothing at all on ship financing (a guaranteed gap).

---

## 6. Testing

84 tests run offline in well under a second:
- **Policies** (search, trust boundary, sufficiency, confidence) are pure functions — tested directly, including the worked confidence examples.
- **Agents** are tested with Pydantic AI's `FunctionModel` playing the LLM: what each agent is shown, and the retry-on-invalid-output behaviour.
- **The workflow** receives its agents as a bundle (dependency injection), so every branch — fallback plan, failed research, short-circuit, failed synthesis, failed verification, exactly one revision, fallback-model warning, bugs not swallowed — is tested with plain fake functions.

What tests with a fake LLM cannot show is answer *quality*; see improvements.

---

## 7. What it fundamentally cannot do

- Know anything outside its document collection, or judge whether a source is right — only how well sources back a statement.
- Guarantee identical briefings for identical questions: control flow is fixed, but LLM wording, and the Planner's breakdown, vary between runs.
- Produce calibrated probabilities. Support levels are explainable rules, not statistics.
- Fully detect subtle misreadings: the Verifier is itself an LLM, and a weaker fallback model verifies less well.

---

## 8. What I would improve with more time

1. **Evaluation harness** — a golden set of questions with expected findings, disagreements and gaps; LLM-as-judge plus deterministic checks; run in CI on every prompt or model change (prompts are already versioned in every `run.json`).
2. **Production retrieval** — hybrid keyword + vector search with a reranker, **entitlement filtering inside the search engine**, and a governed source registry for tier and origin.
3. **Durable execution and human approval** — per-step checkpoints and an approval step for the plan (LangGraph or Temporal), so a crashed run resumes and analysts can steer it.
4. **Observability and cost** — OpenTelemetry / Langfuse tracing, cost per run, alerting on fallback rate and quota.
5. **Model policy** — a stronger or different-family model for the Verifier; refuse to publish (rather than warn) when critical steps ran on a fallback model.
6. **Finer claims** — enforce one fact per claim; weak models sometimes merge sentences, which spreads disagreement penalties further than intended.
7. **Calibrate the policy** — agree weights and labels with analysts and compliance, using the evaluation set.

---

## Project layout

```
src/research_pipeline/
├── app.py, __main__.py   CLI entry point
├── workflows/            the orchestrator: step order, failure policy, trace
├── agents/               the four agents (only package importing pydantic_ai) + shared runner
├── tools/                document search (BM25)
├── policies/             deterministic rules: trust boundary, sufficiency, source quality, confidence
├── memory/               save / load run.json
├── reporting/            RunState → Briefing → markdown
├── llm/                  model configuration (.env) and all prompts (versioned)
└── domain/               every type: research records, LLM contracts, run state, briefing
data/corpus.json          the mock document library
examples/                 committed example runs
tests/                    84 offline tests
scripts/                  connectivity check and step-by-step previews
docs/                     architecture decisions and trade-offs
```
