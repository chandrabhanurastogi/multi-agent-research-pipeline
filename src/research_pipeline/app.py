"""Command-line entry point.

    python -m research_pipeline "Give me an overview of the dry bulk shipping market"
    research-briefing "..."                     (same, via the script in pyproject.toml)

Writes runs/<run_id>/briefing.md (for the analyst) and runs/<run_id>/run.json
(full audit trail), and prints where they are. Exit code 1 only if no briefing
could be produced.
"""

import argparse
import sys
from pathlib import Path

from research_pipeline.agents.runner import configured_model
from research_pipeline.agents.team import build_agents
from research_pipeline.domain.output.briefing import RunStatus
from research_pipeline.domain.state.workflow_state import Severity
from research_pipeline.llm.client import LLMConfigError, fallback_model_names, model_name
from research_pipeline.memory.audit import DEFAULT_RUNS_DIR, run_dir, save_run
from research_pipeline.reporting.briefing_writer import build_briefing, render_markdown
from research_pipeline.tools.search import Corpus
from research_pipeline.workflows.research_briefing import WorkflowCrashed, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Produce a research briefing for an analyst question.")
    parser.add_argument("query", help="the analyst's question, in quotes")
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR, help="where to write outputs")
    args = parser.parse_args(argv)

    try:  # fail fast on configuration, before any work
        model = configured_model()
        models = " -> ".join([model_name(), *fallback_model_names()])
    except LLMConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2

    print(f"Researching: {args.query}\n(using {models}; this takes about a minute)\n")
    crashed = None
    try:
        state = run(args.query, build_agents(model), Corpus.load(), model_name=models)
    except WorkflowCrashed as e:  # a bug: save what we have, then still show the error
        state, crashed = e.state, e

    run_json = save_run(state, args.runs_dir)
    briefing_md = run_dir(state, args.runs_dir) / "briefing.md"
    briefing_md.write_text(render_markdown(build_briefing(state)), encoding="utf-8")

    print(f"Status:   {state.status.value}" + ("   ⚠ needs human review" if state.review_required else ""))
    if state.overall:
        print(f"Support:  {state.overall.label.value}\nCoverage: {state.overall.completeness}")
    for issue in state.issues:
        if issue.severity in (Severity.WARNING, Severity.REVIEW):
            print(f"Note:     {issue.message}")
    print(f"\nBriefing: {briefing_md}\nAudit:    {run_json}")

    if crashed:
        raise crashed.__cause__ from crashed
    return 1 if state.status is RunStatus.FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
