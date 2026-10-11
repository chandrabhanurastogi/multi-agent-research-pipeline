"""Persist a run: runs/<run_id>/run.json (full audit trail) next to briefing.md.

This is the only "memory" the system has: one record per run, written once at
the end (including failed runs). There is no memory across runs.
Production: a database or object store, plus checkpoints after each step so a
crashed run can resume (that is where LangGraph's checkpointer would come in).
"""

from pathlib import Path

from research_pipeline.domain.state.workflow_state import RunState

DEFAULT_RUNS_DIR = Path("runs")


def run_dir(state: RunState, base: Path = DEFAULT_RUNS_DIR) -> Path:
    path = base / state.run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_run(state: RunState, base: Path = DEFAULT_RUNS_DIR) -> Path:
    """Write the full RunState as JSON. Returns the file path."""
    path = run_dir(state, base) / "run.json"
    path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_run(path: Path) -> RunState:
    """Read a saved run back (e.g. to re-render a briefing or investigate a complaint)."""
    return RunState.model_validate_json(path.read_text(encoding="utf-8"))
