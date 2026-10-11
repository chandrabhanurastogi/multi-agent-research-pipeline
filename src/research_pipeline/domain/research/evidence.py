"""Accepted evidence: claims that passed the code checks, and how well each sub-question is covered."""

from enum import StrEnum

from pydantic import Field

from research_pipeline.domain.base import Record


class Coverage(StrEnum):
    """How well one sub-question is evidenced (see policies/sufficiency.py)."""

    COVERED = "covered"  # >= 2 tier A/B sources with different primary_origin
    THIN = "thin"  # 1 independent A/B origin, or only tier C
    GAP = "gap"  # no claims at all


class Claim(Record):
    """A fact that passed the evidence check: the unit of evidence in this system.

    Represents: one fact, from one source, with a quote proven to exist in that source.
    Why it exists: it is the link that makes everything traceable:
        finding -> claim -> quote -> source.
    Validation: ID format (assigned by code). By construction, a Claim is only
        created after policies/trust_boundary.py has confirmed the source exists, it
        was among the documents given to the Researcher, and the quote is found
        in the source text.
    Why a model: immutable and typed, so "accepted" cannot drift after the check.
    Compare with contracts/researcher_output.py:ExtractedClaim, the untrusted LLM version.
    """

    id: str = Field(pattern=r"^C\d+$")
    sub_question_id: str
    source_id: str
    statement: str
    quote: str


class RejectedClaim(Record):
    """A candidate claim that failed the evidence check, kept for the audit trail."""

    sub_question_id: str
    source_id: str
    statement: str
    quote: str
    reason: str  # e.g. "quote not found in S04", "S05 was not provided for this sub-question"
