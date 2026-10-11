"""Run the real workflow end to end and print its trace table (the app prints a summary instead).

    python scripts/try_workflow.py
    python scripts/try_workflow.py "What are the main risks in lithium mining?"
"""

import sys
from pathlib import Path

from research_pipeline.agents.runner import configured_model
from research_pipeline.agents.team import build_agents
from research_pipeline.llm.client import fallback_model_names, model_name
from research_pipeline.tools.search import Corpus
from research_pipeline.workflows.research_briefing import run

DEFAULT_QUERY = "Give me an overview of the dry bulk shipping market and its main risk drivers."


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUERY
    models = " -> ".join([model_name(), *fallback_model_names()])
    state = run(query, build_agents(configured_model()), Corpus.load(), model_name=models)

    out = Path("runs") / f"{state.run_id}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(state.model_dump_json(indent=2))

    print(f"RUN {state.run_id}: {state.status.value}   (review required: {state.review_required})")
    print(f"models: {state.model_name}   prompts: {state.prompt_version}\n")
    print(f"{'step':<14}{'status':<10}{'ms':>7}{'in':>7}{'out':>7}  model / error")
    for s in state.trace:
        detail = s.error or s.model or ""
        print(f"{s.step:<14}{s.status.value:<10}{s.duration_ms:>7}{s.input_tokens:>7}{s.output_tokens:>7}  {detail[:70]}")
    print(f"\ncoverage: { {k: v.value for k, v in state.coverage.items()} }")
    print(f"claims: {len(state.claims)} accepted, {len(state.rejected_claims)} rejected")
    if state.overall:
        print(f"overall: {state.overall.label.value} ({state.overall.score}); {state.overall.completeness}")
    print("\nissues:")
    for i in state.issues:
        print(f"  [{i.severity.value}] {i.step}: {i.message[:120]}")
    print(f"\nfull state saved to {out}")


if __name__ == "__main__":
    main()
