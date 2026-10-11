"""RunState round-trip: a saved run.json must load back into the same state."""

from datetime import datetime

from research_pipeline.domain.state.workflow_state import Issue, IssueKind, RunState, Severity


def test_saved_state_loads_back_including_derived_fields():
    state = RunState(run_id="r1", query="dry bulk overview", model_name="m", started_at=datetime(2026, 10, 1))
    state.add_issue(Issue(kind=IssueKind.VERIFIER_FAILED, step="verify", severity=Severity.REVIEW, message="x"))

    saved = state.model_dump_json()
    assert '"review_required":true' in saved  # derived field is written for readers of run.json

    loaded = RunState.model_validate_json(saved)  # ...and does not break loading
    assert loaded == state and loaded.review_required
