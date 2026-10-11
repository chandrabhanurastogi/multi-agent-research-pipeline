"""Workflow state: the single source of truth for one run. Saved as runs/<run_id>.json."""

from datetime import datetime
from enum import StrEnum

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from research_pipeline.domain.base import Record
from research_pipeline.domain.output.briefing import RunStatus
from research_pipeline.domain.research.evidence import Claim, Coverage, RejectedClaim
from research_pipeline.domain.research.findings import Draft, Verdict
from research_pipeline.domain.research.plan import Interpretation, SubQuestion
from research_pipeline.domain.research.scores import FindingScore, OverallScore
from research_pipeline.domain.research.source import Source


QUERY_MIN_CHARS = 5
QUERY_MAX_CHARS = 1000


class StepStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"  # step failed, a fallback was used, run continued
    FAILED = "failed"  # step failed with no fallback
    SKIPPED = "skipped"  # not run (e.g. after short-circuit)


class IssueKind(StrEnum):
    LLM_UNAVAILABLE = "llm_unavailable"
    INVALID_OUTPUT = "invalid_output"
    CLAIM_REJECTED = "claim_rejected"
    INVALID_REFERENCE = "invalid_reference"
    COVERAGE_GAP = "coverage_gap"
    NO_EVIDENCE = "no_evidence"
    UNVERIFIED_FINDING = "unverified_finding"
    VERIFIER_FAILED = "verifier_failed"
    WEAK_SUPPORT = "weak_support"
    MODEL_FALLBACK = "model_fallback"
    INTERNAL_ERROR = "internal_error"


class Severity(StrEnum):
    INFO = "info"  # shown in the audit trail only
    WARNING = "warning"  # shown to the analyst
    REVIEW = "review"  # shown to the analyst AND sets review_required


class Issue(Record):
    """Something that went wrong or needs the reader's attention.

    Failures are data, not just log lines: they end up in run.json and, by
    severity, in the briefing itself. This is how "degraded" is made explicit.
    """

    kind: IssueKind
    step: str
    severity: Severity
    message: str


class StepRecord(Record):
    """One entry in the run trace: what ran, how long it took, what it cost."""

    step: str
    status: StepStatus
    started_at: datetime
    duration_ms: int = Field(ge=0)
    attempts: int = Field(default=1, ge=1)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    model: str | None = None  # which model answered (LLM steps only)
    fallback_used: bool = False  # answered by a fallback model because earlier ones failed
    error: str | None = None


class RunState(BaseModel):
    """Everything one run has produced so far.

    Represents: the workflow state, the shared record that steps read from and
        that the workflow writes each step's output into.
    Why it exists: one inspectable object instead of values scattered across
        function calls. Reading run.json answers "why does the briefing say this?".
    Validation:
        - validate_assignment=True: every `state.x = value` is validated.
          NOTE: in-place mutation (state.claims.append(...)) is NOT validated,
          so the workflow assigns whole values or uses the add_* helpers.
        - each field is typed with domain records, which validate themselves.
    Why a model, not a dict: a dict lets any step write any key with any shape.
        Here each field has one meaning and one type, and the whole object
        serialises to JSON for audit with one call.

    What is deliberately NOT in state: prompts, raw LLM messages, retry attempts,
    the search index. They are internal to a step; the trace records their cost.
    """

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    # identity
    run_id: str
    query: str = Field(min_length=QUERY_MIN_CHARS, max_length=QUERY_MAX_CHARS)
    model_name: str  # configured primary model (+ fallbacks); per-step actual model is in trace
    prompt_version: str = "unknown"  # llm/prompts.py PROMPT_VERSION, so runs are comparable
    started_at: datetime
    status: RunStatus = RunStatus.RUNNING

    # written by each step, in order
    interpretation: Interpretation | None = None  # Planner
    sub_questions: list[SubQuestion] = Field(default_factory=list)  # Planner
    documents: dict[str, Source] = Field(default_factory=dict)  # search tool
    claims: list[Claim] = Field(default_factory=list)  # Researcher + evidence policy
    rejected_claims: list[RejectedClaim] = Field(default_factory=list)  # evidence policy
    coverage: dict[str, Coverage] = Field(default_factory=dict)  # sufficiency policy
    draft: Draft | None = None  # Synthesiser
    revision_count: int = Field(default=0, ge=0, le=1)  # bounded loop: max 1 revision
    verdicts: list[Verdict] = Field(default_factory=list)  # Verifier
    verified: bool = False  # False if the Verifier failed or was skipped
    finding_scores: list[FindingScore] = Field(default_factory=list)  # confidence policy
    overall: OverallScore | None = None  # confidence policy

    # cross-cutting
    issues: list[Issue] = Field(default_factory=list)
    trace: list[StepRecord] = Field(default_factory=list)

    def add_issue(self, issue: Issue) -> None:
        self.issues = [*self.issues, issue]  # assignment, so it is validated

    def add_step(self, record: StepRecord) -> None:
        self.trace = [*self.trace, record]

    @model_validator(mode="before")
    @classmethod
    def _drop_derived_fields(cls, data: Any) -> Any:
        """Allow a saved run.json to be loaded back.

        review_required is written to JSON (computed_field) but derived from
        issues, so it is dropped on load instead of tripping extra="forbid".
        """
        if isinstance(data, dict):
            data = {k: v for k, v in data.items() if k != "review_required"}
        return data

    @computed_field  # included in run.json
    @property
    def review_required(self) -> bool:
        return any(i.severity is Severity.REVIEW for i in self.issues)
