"""Planner -> search -> Researcher -> trust boundary, on a real query.

    python scripts/try_researcher.py
    python scripts/try_researcher.py "What are the main risks in lithium mining?"

Not part of the pipeline: a step-by-step preview of research. Saves its results for
scripts/try_synthesis.py. The workflow makes
the same calls in the same order, and also records everything in RunState.
"""

import sys
from datetime import date, datetime
from pathlib import Path

from research_pipeline.agents.planner import Planner
from research_pipeline.agents.researcher import Researcher
from research_pipeline.agents.runner import AGENT_ERRORS, configured_model
from research_pipeline.domain.research.plan import SubQuestion
from research_pipeline.domain.state.workflow_state import RunState
from research_pipeline.llm.client import model_name
from research_pipeline.policies.trust_boundary import check_claims
from research_pipeline.tools.search import Corpus

DEFAULT_QUERY = "Give me an overview of the dry bulk shipping market and its main risk drivers."
PREVIEW_FILE = Path("runs/preview_research.json")  # read by scripts/try_synthesis.py


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUERY
    model = configured_model()
    planner, researcher, corpus = Planner(model), Researcher(model), Corpus.load()

    started = datetime.now()
    plan = planner(query, as_of=date.today()).output
    # The workflow will do this: assign code IDs SQ1..SQn
    sub_questions = [
        SubQuestion(id=f"SQ{i}", question=p.question, search_terms=p.search_terms, rationale=p.rationale)
        for i, p in enumerate(plan.sub_questions, start=1)
    ]

    next_claim, total_in, total_out = 1, 0, 0
    all_docs, all_claims, all_rejected = {}, [], []
    for sq in sub_questions:
        docs = corpus.search(f"{sq.question} {' '.join(sq.search_terms)}")
        try:
            result = researcher(sq, docs)
        except AGENT_ERRORS as e:  # failure policy: this sub-question becomes a gap
            print(f"\n{sq.id}: {sq.question}\n  ⚠️  Researcher failed ({type(e).__name__}) -> treated as a GAP, run continues")
            continue
        accepted, rejected = check_claims(sq.id, result.output.claims, docs, first_id=next_claim)
        next_claim += len(accepted)
        all_docs.update({doc.source_id: doc for doc in docs})
        all_claims += accepted
        all_rejected += rejected
        total_in, total_out = total_in + result.input_tokens, total_out + result.output_tokens

        print(f"\n{sq.id}: {sq.question}")
        print(f"  documents given: {[d.source_id for d in docs]}")
        print(f"  LLM returned {len(result.output.claims)} candidate claims "
              f"({result.requests} request(s)) -> {len(accepted)} accepted, {len(rejected)} rejected")
        for c in accepted:
            print(f"    ✅ {c.id} [{c.source_id}] {c.statement}")
            print(f"         quote: \"{c.quote}\"")
        for r in rejected:
            print(f"    ❌ [{r.source_id}] {r.statement}")
            print(f"         quote: \"{r.quote}\"  -> {r.reason}")

    print(f"\nUSAGE (researcher calls only): {total_in} in / {total_out} out tokens")

    # Save what we have as a (partial) RunState: the same object the workflow will build.
    state = RunState(
        run_id="preview", query=query, model_name=model_name(), started_at=started,
        interpretation=plan.interpretation, sub_questions=sub_questions,
        documents=all_docs, claims=all_claims, rejected_claims=all_rejected,
    )
    PREVIEW_FILE.parent.mkdir(exist_ok=True)
    PREVIEW_FILE.write_text(state.model_dump_json(indent=2))
    print(f"Saved partial RunState to {PREVIEW_FILE} (input for scripts/try_synthesis.py)")


if __name__ == "__main__":
    main()
