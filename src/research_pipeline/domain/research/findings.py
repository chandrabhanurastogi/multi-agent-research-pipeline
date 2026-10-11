"""The draft briefing content and the Verifier's judgement on it."""

from enum import StrEnum

from pydantic import Field

from research_pipeline.domain.base import LLMOutput, Record


class Disagreement(LLMOutput):
    """Two or more claims that disagree. Written by the Synthesiser, kept as-is in the Draft."""

    description: str = Field(min_length=5)
    claim_ids: list[str] = Field(min_length=2, description="The claims that disagree")


class Finding(Record):
    """A draft finding with a code-assigned ID (F1..), so the Verifier can refer to it."""

    id: str = Field(pattern=r"^F\d+$")
    statement: str
    claim_ids: list[str] = Field(min_length=1)


class Draft(Record):
    """The current draft briefing content (after IDs are assigned and references checked)."""

    summary: str
    findings: list[Finding]
    disagreements: list[Disagreement]
    follow_up_questions: list[str]


class VerdictStatus(StrEnum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"


class Verdict(LLMOutput):
    """The Verifier's judgement on one finding.

    Represents: whether the cited evidence backs the finding, which cited claims
        actually support it, and which claims contradict it.
    Why it exists: the scorer uses supporting_claim_ids, not the Synthesiser's
        citations, so only support the Verifier confirmed is counted.
    Validation here: shape only. policies/trust_boundary.py then enforces, in code:
        - supporting_claim_ids must be a SUBSET of the finding's cited claim_ids
          (the Verifier may remove support, never add it);
        - every referenced claim/finding ID must exist.
    Why a model: these IDs feed the confidence calculation; they must be valid.
    Why it lives in research/, not contracts/: it is both LLM output AND a
        record kept in state and used by the scorer.
    """

    finding_id: str
    status: VerdictStatus
    supporting_claim_ids: list[str] = Field(default_factory=list)
    contradicting_claim_ids: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=3)
    suggested_rewrite: str | None = Field(
        default=None, description="Optional better wording; the Synthesiser decides whether to use it"
    )
