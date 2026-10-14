"""The research briefing workflow: a fixed sequence of steps with explicit failure handling.

    run(query) -> RunState

    1 PLAN        Planner                     fails -> fallback: research the query as one sub-question
    2 RESEARCH    search + Researcher + check fails -> that sub-question has no evidence (gap)
    3 SUFFICIENCY coverage per sub-question   no credible evidence -> SHORT-CIRCUIT (stop here)
    4 SYNTHESISE  Synthesiser + check_draft   fails -> run FAILED (nothing to show)
    5 VERIFY      Verifier + check_verdicts   fails -> continue UNVERIFIED, review required
      REVISE      at most once, if any finding is not fully supported (BOUNDED LOOP)
    6 SCORE       confidence policy           pure code, cannot fail on valid state

Control flow is deterministic: the same steps in the same order every run. Only the
content (what the LLM writes) varies. Agents, search and policies never touch
RunState: they take inputs and return outputs, and this module writes them into state.
"""

import time
import uuid
from datetime import date, datetime

from research_pipeline.agents.runner import AGENT_ERRORS
from research_pipeline.agents.team import Agents
from research_pipeline.domain.contracts.agent_result import AgentResult
from research_pipeline.domain.output.briefing import RunStatus
from research_pipeline.domain.research.evidence import Claim, Coverage
from research_pipeline.domain.research.findings import Draft, Verdict, VerdictStatus
from research_pipeline.domain.research.plan import Interpretation, SubQuestion
from research_pipeline.domain.research.scores import SupportLabel
from research_pipeline.domain.research.source import Source
from research_pipeline.domain.state.workflow_state import Issue, IssueKind, RunState, Severity, StepRecord, StepStatus
from research_pipeline.llm.prompts import PROMPT_VERSION
from research_pipeline.policies.confidence import score_findings, score_overall
from research_pipeline.policies.sufficiency import assess_coverage, has_credible_evidence
from research_pipeline.policies.trust_boundary import check_claims, check_draft, check_verdicts
from research_pipeline.tools.search import Corpus

MAX_REVISIONS = 1


class WorkflowCrashed(Exception):
    """An unexpected error (a bug, not an LLM failure) stopped the run.

    Carries the partial RunState so the caller can still save the audit trail.
    The original exception is chained as __cause__, so the bug is not hidden.
    """

    def __init__(self, state: RunState) -> None:
        super().__init__(f"run {state.run_id} crashed; partial state attached")
        self.state = state


def run(query: str, agents: Agents, corpus: Corpus, *, model_name: str = "unknown", as_of: date | None = None) -> RunState:
    """Run the whole pipeline and return its RunState.

    Agent failures never escape: each step applies its failure policy and records
    an Issue. Anything else is a bug: the state is marked FAILED and re-raised
    inside WorkflowCrashed, so the caller can save it and still see the error.
    """
    state = RunState(
        run_id=f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}",
        query=query,
        model_name=model_name,
        prompt_version=PROMPT_VERSION,
        started_at=datetime.now(),
    )
    try:
        return _run_steps(state, agents, corpus, as_of or date.today())
    except Exception as e:
        _issue(state, IssueKind.INTERNAL_ERROR, "run", Severity.REVIEW, f"Unexpected error: {type(e).__name__}: {e}")
        state.status = RunStatus.FAILED
        raise WorkflowCrashed(state) from e


def _run_steps(state: RunState, agents: Agents, corpus: Corpus, as_of: date) -> RunState:
    _plan(state, agents, as_of)
    _research(state, agents, corpus)
    if not _sufficient(state, as_of):
        return _finish(state, RunStatus.INSUFFICIENT_EVIDENCE)
    if not _synthesise(state, agents):
        return _finish(state, RunStatus.FAILED)
    _verify_and_revise(state, agents)
    _score(state, as_of)
    return _finish(state)


# --- Steps ---------------------------------------------------------------------


def _plan(state: RunState, agents: Agents, as_of: date) -> None:
    result = _call(state, "plan", StepStatus.DEGRADED, agents.planner, state.query, as_of)
    if result is None:
        # Fallback: research the question as a whole rather than stopping.
        _issue(state, IssueKind.LLM_UNAVAILABLE, "plan", Severity.WARNING,
               "Planning failed, so the question was researched as a whole instead of being broken down.")
        state.interpretation = Interpretation(
            restated_question=f"Original question: {state.query}",
            scope="Not determined (planning failed)",
            assumptions=["The question was researched as a whole because planning failed."],
        )
        state.sub_questions = [
            SubQuestion(id="SQ1", question=state.query, search_terms=[state.query], rationale="fallback plan")
        ]
        return
    state.interpretation = result.output.interpretation
    state.sub_questions = [  # code assigns IDs, never the LLM
        SubQuestion(id=f"SQ{i}", question=p.question, search_terms=p.search_terms, rationale=p.rationale)
        for i, p in enumerate(result.output.sub_questions, start=1)
    ]


def _research(state: RunState, agents: Agents, corpus: Corpus) -> None:
    documents: dict[str, Source] = {}
    claims: list[Claim] = []
    rejected = []
    for sq in state.sub_questions:
        docs = corpus.search(f"{sq.question} {' '.join(sq.search_terms)}")
        documents.update({d.source_id: d for d in docs})
        if not docs:
            continue  # nothing to read: no LLM call, the sub-question becomes a gap
        result = _call(state, f"research:{sq.id}", StepStatus.DEGRADED, agents.researcher, sq, docs)
        if result is None:
            _issue(state, IssueKind.LLM_UNAVAILABLE, f"research:{sq.id}", Severity.WARNING,
                   f"Research for '{sq.question}' failed, so it is treated as having no evidence.")
            continue
        accepted, rej = check_claims(sq.id, result.output.claims, docs, first_id=len(claims) + 1)
        claims += accepted
        rejected += rej
    state.documents, state.claims, state.rejected_claims = documents, claims, rejected
    if rejected:
        _issue(state, IssueKind.CLAIM_REJECTED, "research", Severity.INFO,
               f"{len(rejected)} extracted claim(s) rejected by the evidence check (see rejected_claims).")


def _sufficient(state: RunState, as_of: date) -> bool:
    state.coverage = assess_coverage(state.sub_questions, state.claims, state.documents, as_of)


    # Creates a new list containing only the SubQuestion objects that have zero evidence.\
    gaps = [sq for sq in state.sub_questions if state.coverage[sq.id] is Coverage.GAP]
    if gaps:
        # If MORE THAN HALF the questions have zero evidence, flag for human review
        severity = Severity.REVIEW if len(gaps) * 2 > len(state.sub_questions) else Severity.WARNING

        # Log an issue listing the exact unanswered questions
        _issue(state, IssueKind.COVERAGE_GAP, "sufficiency", severity,
               "No evidence found for: " + "; ".join(sq.question for sq in gaps))
    if has_credible_evidence(state.claims, state.documents, as_of):
        return True
    _issue(state, IssueKind.NO_EVIDENCE, "sufficiency", Severity.REVIEW,
           "No credible (tier A/B, recent) evidence was found, so no briefing was written.")
    for step in ("synthesise", "verify"):
        state.add_step(StepRecord(step=step, status=StepStatus.SKIPPED, started_at=datetime.now(), duration_ms=0))
    return False


def _synthesise(state: RunState, agents: Agents) -> bool:
    result = _call(state, "synthesise", StepStatus.FAILED, agents.synthesiser,
                   state.interpretation, state.sub_questions, state.coverage, state.claims, state.documents)
    if result is None:
        _issue(state, IssueKind.LLM_UNAVAILABLE, "synthesise", Severity.REVIEW, "Writing the briefing failed.")
        return False
    draft = _accept_draft(state, result, "synthesise")
    if draft is None:
        return False
    state.draft = draft
    return True


def _verify_and_revise(state: RunState, agents: Agents) -> None:
    verdicts = _verify(state, agents, state.draft, "verify")

    if verdicts is not None and _needs_revision(state.draft, verdicts) and state.revision_count < MAX_REVISIONS:
        result = _call(state, "revise", StepStatus.DEGRADED, agents.synthesiser,
                       state.interpretation, state.sub_questions, state.coverage, state.claims, state.documents,
                       previous=state.draft, feedback=verdicts)
        revised = _accept_draft(state, result, "revise") if result else None
        if revised is None:
            _issue(state, IssueKind.LLM_UNAVAILABLE, "revise", Severity.WARNING,
                   "Revision failed; the first draft and its review are kept.")
        else:
            state.draft, state.revision_count = revised, state.revision_count + 1
            verdicts = _verify(state, agents, revised, "re-verify")

    if verdicts is None:
        state.verified = False
        _issue(state, IssueKind.VERIFIER_FAILED, "verify", Severity.REVIEW,
               "The independent check of the briefing failed; all findings are shown as weakly supported.")
        return
    state.verdicts, state.verified = verdicts, True
    by_id = {v.finding_id: v for v in verdicts}
    unsupported = [f for f in state.draft.findings if f.id in by_id and by_id[f.id].status is VerdictStatus.UNSUPPORTED]
    unchecked = [f for f in state.draft.findings if f.id not in by_id]
    if unsupported:
        _issue(state, IssueKind.UNVERIFIED_FINDING, "verify", Severity.REVIEW,
               f"{len(unsupported)} statement(s) were not backed by the quoted sources and were excluded "
               "from key findings.")
    if unchecked:  # no verdict returned: kept, but scored as not verified (capped at Weakly supported)
        _issue(state, IssueKind.UNVERIFIED_FINDING, "verify", Severity.REVIEW,
               f"{len(unchecked)} statement(s) were not checked by the reviewer; they are shown as weakly supported.")


def _score(state: RunState, as_of: date) -> None:
    verdicts = state.verdicts if state.verified else None
    state.finding_scores = score_findings(state.draft, verdicts, state.claims, state.documents, as_of)
    state.overall = score_overall(state.finding_scores, state.coverage)
    if state.overall.label is SupportLabel.WEAK:
        _issue(state, IssueKind.WEAK_SUPPORT, "score", Severity.REVIEW,
               "Overall, the findings are only weakly supported by the sources.")


# --- Helpers -------------------------------------------------------------------


def _verify(state: RunState, agents: Agents, draft: Draft, step: str) -> list[Verdict] | None:
    result = _call(state, step, StepStatus.DEGRADED, agents.verifier, draft, state.claims, state.documents)
    if result is None:
        return None
    verdicts, problems = check_verdicts(result.output.verdicts, draft, {c.id for c in state.claims})
    for p in problems:
        _issue(state, IssueKind.INVALID_REFERENCE, step, Severity.INFO, p)
    return verdicts


def _accept_draft(state: RunState, result: AgentResult, step: str) -> Draft | None:
    draft, problems = check_draft(result.output, {c.id for c in state.claims})
    for p in problems:
        _issue(state, IssueKind.INVALID_REFERENCE, step, Severity.INFO, p)
    if not draft.findings:
        _issue(state, IssueKind.INVALID_OUTPUT, step, Severity.REVIEW,
               "No statement in the draft cited valid evidence.")
        return None
    return draft


def _needs_revision(draft: Draft, verdicts: list[Verdict]) -> bool:
    by_id = {v.finding_id: v for v in verdicts}
    return any(f.id not in by_id or by_id[f.id].status is not VerdictStatus.SUPPORTED for f in draft.findings)


def _call(state: RunState, step: str, on_failure: StepStatus, agent, *args, **kwargs) -> AgentResult | None:
    """Call one agent, record a trace entry, and turn agent failures into None.

    Only AGENT_ERRORS (provider down, all fallbacks failed, output still invalid)
    are caught. Anything else is a bug and propagates.
    """
    started, t0 = datetime.now(), time.perf_counter()
    try:
        result = agent(*args, **kwargs)
    except AGENT_ERRORS as e:
        state.add_step(StepRecord(step=step, status=on_failure, started_at=started, duration_ms=_ms(t0),
                                  error=f"{type(e).__name__}: {str(e)[:300]}"))
        return None
    state.add_step(StepRecord(step=step, status=StepStatus.OK, started_at=started, duration_ms=_ms(t0),
                              attempts=result.requests, input_tokens=result.input_tokens,
                              output_tokens=result.output_tokens, model=result.model,
                              fallback_used=result.fallback_used))
    return result


def _issue(state: RunState, kind: IssueKind, step: str, severity: Severity, message: str) -> None:
    state.add_issue(Issue(kind=kind, step=step, severity=severity, message=message))


def _finish(state: RunState, status: RunStatus | None = None) -> RunState:
    fallback_steps = [s.step for s in state.trace if s.fallback_used]
    models = sorted({s.model for s in state.trace if s.model})
    if fallback_steps or len(models) > 1:
        # With a fallback chain, provider errors can silently move work to a weaker model.
        _issue(state, IssueKind.MODEL_FALLBACK, "run", Severity.WARNING,
               f"{len(fallback_steps)} of {sum(1 for s in state.trace if s.model)} AI steps were answered by a "
               f"fallback model because the preferred model was unavailable (models used: {', '.join(models)}). "
               "Quality may be lower than usual.")
    if status is None:
        failed = any(s.status in (StepStatus.DEGRADED, StepStatus.FAILED) for s in state.trace)
        status = RunStatus.DEGRADED if failed else RunStatus.COMPLETED
    state.status = status
    return state


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)
