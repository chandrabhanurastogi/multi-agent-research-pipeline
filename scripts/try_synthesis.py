"""Synthesiser -> Verifier -> (one revision) -> confidence, on saved research.

    python scripts/try_researcher.py      # once: saves runs/preview_research.json
    python scripts/try_synthesis.py       # as often as you like: reuses that research

Not part of the pipeline: a step-by-step preview of writing and checking. The workflow makes
the same calls in the same order, with failure handling and a trace.
"""

import sys
from datetime import date
from pathlib import Path

from fake_llm import configured_model  # LLM_MODEL=fake -> no API calls
from research_pipeline.agents.synthesiser import Synthesiser
from research_pipeline.agents.verifier import Verifier
from research_pipeline.domain.research.findings import Draft, Verdict, VerdictStatus
from research_pipeline.domain.state.workflow_state import RunState
from research_pipeline.policies.confidence import score_findings, score_overall
from research_pipeline.policies.sufficiency import assess_coverage
from research_pipeline.policies.trust_boundary import check_draft, check_verdicts

ROOT = Path(__file__).resolve().parents[1]  # repo root, so the script works from any directory
PREVIEW_FILE = ROOT / "runs" / "preview_research.json"


def show(draft: Draft, verdicts: list[Verdict], problems: list[str], title: str) -> None:
    by_id = {v.finding_id: v for v in verdicts}
    print(f"\n=== {title} ===")
    for f in draft.findings:
        v = by_id.get(f.id)
        status = v.status.value.upper() if v else "NO VERDICT"
        print(f"  {f.id} {f.claim_ids} {status}\n     {f.statement}")
        if v and v.status is not VerdictStatus.SUPPORTED:
            print(f"     reviewer: {v.reason}")
            if v.suggested_rewrite:
                print(f"     suggests: {v.suggested_rewrite}")
        if v and v.contradicting_claim_ids:
            print(f"     contradicted by: {v.contradicting_claim_ids}")
    for p in problems:
        print(f"  ! {p}")


def main() -> None:
    if not PREVIEW_FILE.exists():
        sys.exit(f"{PREVIEW_FILE} not found: run scripts/try_researcher.py first.")
    state = RunState.model_validate_json(PREVIEW_FILE.read_text())
    if not state.claims:
        # The workflow stops here too (insufficient evidence): there is nothing to write from.
        sys.exit(f"The saved research for '{state.query}' has no accepted claims, so there is nothing to "
                 "synthesise.\nRe-run scripts/try_researcher.py with a question the corpus covers (dry bulk shipping).")
    as_of, sources, claim_ids = date.today(), state.documents, {c.id for c in state.claims}
    model = configured_model()
    synthesiser, verifier = Synthesiser(model), Verifier(model)

    coverage = assess_coverage(state.sub_questions, state.claims, sources, as_of)
    print(f"QUERY: {state.query}\nCOVERAGE: { {k: v.value for k, v in coverage.items()} }")
    print(f"CLAIMS: {len(state.claims)} accepted from research")

    # 1. write
    out = synthesiser(state.interpretation, state.sub_questions, coverage, state.claims, sources).output
    draft, draft_problems = check_draft(out, claim_ids)
    # 2. check
    raw = verifier(draft, state.claims, sources).output.verdicts
    verdicts, verdict_problems = check_verdicts(raw, draft, claim_ids)
    show(draft, verdicts, draft_problems + verdict_problems, "DRAFT 1 + VERIFIER")

    # 3. bounded loop: revise at most once
    if any(v.status is not VerdictStatus.SUPPORTED for v in verdicts):
        out = synthesiser(state.interpretation, state.sub_questions, coverage, state.claims, sources,
                          previous=draft, feedback=verdicts).output
        draft, draft_problems = check_draft(out, claim_ids)
        raw = verifier(draft, state.claims, sources).output.verdicts
        verdicts, verdict_problems = check_verdicts(raw, draft, claim_ids)
        show(draft, verdicts, draft_problems + verdict_problems, "DRAFT 2 (REVISED) + VERIFIER")

    # 4. score (code, not LLM)
    scores = score_findings(draft, verdicts, state.claims, sources, as_of)
    overall = score_overall(scores, coverage)
    statements = {f.id: f.statement for f in draft.findings}
    print("\n=== BRIEFING PREVIEW ===")
    print(f"SUMMARY: {draft.summary}\n")
    print(f"OVERALL SUPPORT: {overall.label.value} ({overall.score})")
    print(f"COMPLETENESS:    {overall.completeness}")
    for r in overall.reasons:
        print(f"  - {r}")
    print("\nKEY FINDINGS")
    for s in scores:
        print(f"  [{s.label.value}, {s.score}] {statements[s.finding_id]}\n      why: {s.explanation}")
    excluded = [f for f in draft.findings if f.id not in {s.finding_id for s in scores}]
    if excluded:
        print("\nCLAIMS WE COULD NOT VERIFY")
        for f in excluded:
            print(f"  - {f.statement}")
    if draft.disagreements:
        print("\nWHERE SOURCES DISAGREE")
        for d in draft.disagreements:
            print(f"  - {d.description} {d.claim_ids}")
    print("\nFOLLOW-UP QUESTIONS")
    for q in draft.follow_up_questions:
        print(f"  - {q}")


if __name__ == "__main__":
    main()
