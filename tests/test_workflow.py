"""Workflow tests: every branch of the control flow, with FAKE agents (tests/fakes.py).

The fakes are plain functions returning AgentResult: no LLM, no Pydantic AI, no
network. This is possible because the workflow receives its agents as an
`Agents` bundle (dependency injection) instead of creating them.

Each test answers: "if THIS happens, what does the run do and record?"
"""

from datetime import date

import pytest
from fakes import QUERY, agents, fake_planner, fake_researcher, fake_synthesiser, provider_down, verifier_saying

from research_pipeline.domain.output.briefing import RunStatus
from research_pipeline.domain.research.findings import VerdictStatus
from research_pipeline.domain.state.workflow_state import IssueKind, StepStatus
from research_pipeline.tools.search import Corpus
from research_pipeline.workflows.research_briefing import WorkflowCrashed, run

AS_OF = date(2026, 10, 1)


@pytest.fixture(scope="module")
def corpus():
    return Corpus.load()


def steps(state) -> list[tuple[str, StepStatus]]:
    return [(s.step, s.status) for s in state.trace]


def kinds(state) -> set[IssueKind]:
    return {i.kind for i in state.issues}


# --- Happy path ----------------------------------------------------------------------


def test_happy_path_runs_every_step_once(corpus):
    state = run(QUERY, agents(), corpus, as_of=AS_OF)
    assert state.status is RunStatus.COMPLETED
    assert [s for s, _ in steps(state)] == ["plan", "research:SQ1", "research:SQ2", "research:SQ3", "synthesise", "verify"]
    assert state.verified and state.revision_count == 0
    assert [sq.id for sq in state.sub_questions] == ["SQ1", "SQ2", "SQ3"]  # code-assigned IDs
    assert len(state.finding_scores) == 3 and state.overall is not None
    assert all(s.model == "fake" and s.input_tokens == 10 for s in state.trace)


def test_saved_state_round_trips(corpus):
    from research_pipeline.domain.state.workflow_state import RunState

    state = run(QUERY, agents(), corpus, as_of=AS_OF)
    assert RunState.model_validate_json(state.model_dump_json()) == state


# --- Failure policies ------------------------------------------------------------------


def test_planner_failure_falls_back_to_researching_the_whole_question(corpus):
    state = run(QUERY, agents(planner=provider_down), corpus, as_of=AS_OF)
    assert steps(state)[0] == ("plan", StepStatus.DEGRADED)
    assert [sq.question for sq in state.sub_questions] == [QUERY]
    assert state.status is RunStatus.DEGRADED and state.draft is not None


def test_one_researcher_failure_becomes_a_gap_and_run_continues(corpus):
    calls = []

    def flaky(sub_question, docs):
        calls.append(sub_question.id)
        return provider_down() if sub_question.id == "SQ2" else fake_researcher(sub_question, docs)

    state = run(QUERY, agents(researcher=flaky), corpus, as_of=AS_OF)
    assert calls == ["SQ1", "SQ2", "SQ3"]  # did not stop at SQ2
    assert state.coverage["SQ2"].value == "gap"
    assert IssueKind.LLM_UNAVAILABLE in kinds(state)
    assert state.status is RunStatus.DEGRADED and state.draft is not None


def test_no_credible_evidence_short_circuits(corpus):
    state = run(QUERY, agents(researcher=provider_down), corpus, as_of=AS_OF)
    assert state.status is RunStatus.INSUFFICIENT_EVIDENCE
    assert ("synthesise", StepStatus.SKIPPED) in steps(state) and state.draft is None
    assert IssueKind.NO_EVIDENCE in kinds(state) and state.review_required


def test_synthesiser_failure_fails_the_run_but_keeps_state(corpus):
    state = run(QUERY, agents(synthesiser=provider_down), corpus, as_of=AS_OF)
    assert state.status is RunStatus.FAILED
    assert state.claims  # research results are still there for the audit trail
    assert state.review_required


def test_verifier_failure_continues_unverified_and_caps_scores(corpus):
    state = run(QUERY, agents(verifier=provider_down), corpus, as_of=AS_OF)
    assert not state.verified and state.status is RunStatus.DEGRADED
    assert all(s.score <= 0.39 for s in state.finding_scores)
    assert IssueKind.VERIFIER_FAILED in kinds(state) and state.review_required


# --- Bounded revision loop ---------------------------------------------------------------


def test_partial_verdict_triggers_exactly_one_revision(corpus):
    synth_calls, verdict_queue = [], [VerdictStatus.PARTIAL, VerdictStatus.SUPPORTED]

    def counting_synth(*args, **kwargs):
        synth_calls.append(kwargs.get("previous") is not None)
        return fake_synthesiser(*args, **kwargs)

    def verifier(draft, claims, sources):
        return verifier_saying(verdict_queue.pop(0))(draft, claims, sources)

    state = run(QUERY, agents(synthesiser=counting_synth, verifier=verifier), corpus, as_of=AS_OF)
    assert synth_calls == [False, True]  # first draft, then one revision with feedback
    assert [s for s, _ in steps(state)][-4:] == ["synthesise", "verify", "revise", "re-verify"]
    assert state.revision_count == 1 and state.status is RunStatus.COMPLETED


def test_revision_happens_at_most_once(corpus):
    synth_calls = []

    def counting_synth(*args, **kwargs):
        synth_calls.append(1)
        return fake_synthesiser(*args, **kwargs)

    state = run(QUERY, agents(synthesiser=counting_synth, verifier=verifier_saying(VerdictStatus.UNSUPPORTED)),
                corpus, as_of=AS_OF)
    assert len(synth_calls) == 2  # never a third time, however bad the verdicts
    assert state.finding_scores == []  # unsupported findings are excluded
    assert IssueKind.UNVERIFIED_FINDING in kinds(state) and state.review_required


# --- Bugs are not swallowed -----------------------------------------------------------------


def test_unexpected_error_is_not_swallowed_but_state_is_kept(corpus):
    def buggy(*_):
        raise KeyError("a bug, not an LLM failure")

    with pytest.raises(WorkflowCrashed) as crash:
        run(QUERY, agents(researcher=buggy), corpus, as_of=AS_OF)
    assert isinstance(crash.value.__cause__, KeyError)  # the bug is still visible
    state = crash.value.state  # ...and the partial state can still be saved
    assert state.status is RunStatus.FAILED and state.sub_questions and state.review_required


def test_steps_answered_by_a_fallback_model_are_flagged(corpus):
    def fallback_researcher(sub_question, docs):
        result = fake_researcher(sub_question, docs)
        return result.model_copy(update={"model": "weaker-fallback-model", "fallback_used": True})

    state = run(QUERY, agents(researcher=fallback_researcher), corpus, as_of=AS_OF)
    [issue] = [i for i in state.issues if i.kind is IssueKind.MODEL_FALLBACK]
    assert "3 of 6 AI steps" in issue.message and "weaker-fallback-model" in issue.message
    assert [s.step for s in state.trace if s.fallback_used] == ["research:SQ1", "research:SQ2", "research:SQ3"]


def test_every_step_on_one_fallback_model_is_still_flagged(corpus):
    # The case that slipped through in a real run: one model answered everything,
    # but it was the last fallback, not the preferred model.
    def via_fallback(agent):
        def call(*args, **kwargs):
            return agent(*args, **kwargs).model_copy(update={"fallback_used": True})
        return call

    state = run(QUERY, agents(planner=via_fallback(fake_planner), researcher=via_fallback(fake_researcher),
                              synthesiser=via_fallback(fake_synthesiser),
                              verifier=via_fallback(verifier_saying(VerdictStatus.SUPPORTED))),
                corpus, as_of=AS_OF)
    assert IssueKind.MODEL_FALLBACK in kinds(state)


def test_finding_without_a_verdict_is_kept_but_weak_and_flagged(corpus):
    def verifier_skipping_last(draft, claims, sources):
        result = verifier_saying(VerdictStatus.SUPPORTED)(draft, claims, sources)
        return result.model_copy(update={"output": result.output.model_copy(update={"verdicts": result.output.verdicts[:-1]})})

    state = run(QUERY, agents(verifier=verifier_skipping_last), corpus, as_of=AS_OF)
    last = state.draft.findings[-1].id
    [score] = [s for s in state.finding_scores if s.finding_id == last]
    assert score.score <= 0.39 and "NOT verified" in score.explanation
    assert any("not checked by the reviewer" in i.message for i in state.issues)
