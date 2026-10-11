# Example runs

Each folder holds the two files one run produces: `briefing.md` (what the analyst reads) and `run.json` (the full audit trail: plan, every document retrieved, every claim with its exact quote, verdicts, score breakdowns, issues, and a per-step trace with timings, tokens and the model that answered).

Both runs were produced with `python -m research_pipeline "<question>"`. On the day they were generated, the free-tier quota of the preferred models was exhausted, so every step was answered by the fallback model `gemini-3.1-flash-lite` — and each briefing says so in its **Notes**.

## 01 — Dry bulk overview (the brief's example question)

[`01_dry_bulk_overview/briefing.md`](01_dry_bulk_overview/briefing.md) · status **completed** · 6 LLM calls · ~10k tokens

What to look for:
- **Disagreement surfaced, not resolved:** orderbook 7% (Harbourline) vs 10% (Meridian) under "Where sources disagree".
- **Attribution does not hide a dispute:** findings 2 and 3 take one side of a recorded disagreement, so they score 0.20 ("Weakly supported") with "1 source disagrees" (ARCHITECTURE.md §13.5).
- **Support and completeness reported separately:** "Partly supported (0.44)" vs "3 of 3 areas answered".
- **Every finding names its sources and why it got its label** ("Best source: official or industry body; not independently confirmed; ...").
- **Honest about operating conditions:** the Notes say all steps ran on a fallback model. The cost is visible: the lite model's plan had no sub-question on Chinese iron-ore demand, so the strongest evidence in the corpus (S01, S02) never reached the findings — and a follow-up question asks about it.

## 02 — A question the corpus cannot answer

[`02_unanswerable_question/briefing.md`](02_unanswerable_question/briefing.md) · status **insufficient_evidence** · needs human review

Question: *"What are the main operational risks for offshore wind farm developers in the North Sea?"* — the mock corpus is about dry bulk shipping.

What to look for:
- Keyword search still returned loosely matching documents, but the Researcher extracted **no** relevant claims, so all four sub-questions became **gaps**.
- With no credible evidence, the workflow **short-circuited**: no Synthesiser or Verifier call, no invented briefing.
- The briefing says so plainly, is flagged **Needs human review**, and turns each gap into a follow-up question.
