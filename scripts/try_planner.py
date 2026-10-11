"""Run the Planner on a real query and show what search finds for each sub-question.

    python scripts/try_planner.py
    python scripts/try_planner.py "What are the main risks in lithium mining?"

Not part of the pipeline: a step-by-step preview of the Planner. The workflow makes
the same calls in the same order.
"""

import sys
from datetime import date

from research_pipeline.agents.planner import Planner
from research_pipeline.agents.runner import configured_model
from research_pipeline.tools.search import Corpus

DEFAULT_QUERY = "Give me an overview of the dry bulk shipping market and its main risk drivers."


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUERY
    planner = Planner(configured_model())
    corpus = Corpus.load()

    result = planner(query, as_of=date.today())
    plan = result.output

    print(f"QUERY: {query}\n")
    print("INTERPRETATION")
    print(f"  restated:    {plan.interpretation.restated_question}")
    print(f"  scope:       {plan.interpretation.scope}")
    for a in plan.interpretation.assumptions:
        print(f"  assumption:  {a}")

    print("\nSUB-QUESTIONS  (+ what search returns for each)")
    for i, sq in enumerate(plan.sub_questions, start=1):
        docs = corpus.search(f"{sq.question} {' '.join(sq.search_terms)}")
        print(f"  SQ{i}: {sq.question}")
        print(f"       terms:     {sq.search_terms}")
        print(f"       why:       {sq.rationale}")
        print(f"       documents: {[d.source_id for d in docs] or 'none'}")

    print(f"\nUSAGE: {result.input_tokens} in / {result.output_tokens} out tokens, "
          f"{result.requests} request(s){'  <- retried after invalid output' if result.requests > 1 else ''}")


if __name__ == "__main__":
    main()
