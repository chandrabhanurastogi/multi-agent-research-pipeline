"""The analyst-facing product, and the run outcome it reports."""

from datetime import date, datetime
from enum import StrEnum

from pydantic import Field

from research_pipeline.domain.base import Record
from research_pipeline.domain.research.plan import Interpretation
from research_pipeline.domain.research.scores import OverallScore, SupportLabel
from research_pipeline.domain.research.source import Tier


class RunStatus(StrEnum):
    """Outcome of a run. Stored in RunState and printed on the briefing."""

    RUNNING = "running"
    COMPLETED = "completed"  # every step succeeded
    DEGRADED = "degraded"  # briefing produced, but a step failed or was skipped (see issues)
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"  # short-circuit: nothing credible found
    FAILED = "failed"  # no briefing could be produced; state is still saved


class SourceRef(Record):
    source_id: str
    title: str
    publisher: str
    tier: Tier
    published: date


class BriefingFinding(Record):
    statement: str
    support: SupportLabel
    score: float = Field(ge=0.0, le=1.0)
    explanation: str
    sources: list[SourceRef] = Field(min_length=1)


class Briefing(Record):
    """The analyst-facing briefing, assembled by code from RunState.

    Represents: the output contract with the reader: fixed sections, fixed order.
    Why it exists separately from RunState: RunState is for engineers and auditors
        (everything, including rejected claims and token counts). Briefing is for
        analysts (only what they need, in plain language). Keeping them separate
        means the renderer cannot accidentally leak internals, and the layout is
        identical on every run even when content varies.
    Validation: every key finding has a support label and at least one source.
        Unsupported findings are not allowed here; they go to unverified_claims.
    Why a model: the renderer (markdown today, maybe HTML or an API later) depends
        only on this contract.
    """

    run_id: str
    generated_at: datetime
    query: str
    status: RunStatus
    verified: bool
    interpretation: Interpretation | None
    overall: OverallScore | None
    summary: str
    key_findings: list[BriefingFinding]
    disagreements: list[str]
    gaps: list[str]  # "What we could not establish"
    unverified_claims: list[str]  # "Claims we could not verify"
    follow_up_questions: list[str]
    review_required: bool
    review_reasons: list[str]  # issues with severity REVIEW
    notes: list[str]  # issues with severity WARNING: worth knowing, no review needed
    sources: list[SourceRef]
    model_name: str  # configured chain
    models_used: list[str]  # models that actually answered, from the trace
    prompt_version: str
