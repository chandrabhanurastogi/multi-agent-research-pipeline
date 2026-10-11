"""Confidence results. Computed by policies/confidence.py; every number carries its breakdown."""

from enum import StrEnum

from pydantic import Field

from research_pipeline.domain.base import Record


class SupportLabel(StrEnum):
    """What analysts see instead of HIGH/MEDIUM/LOW (ARCHITECTURE.md section 13.2)."""

    STRONG = "Strongly supported by our sources"
    PARTIAL = "Partly supported by our sources"
    WEAK = "Weakly supported - treat with caution"


class FindingScore(Record):
    """Confidence for one finding, with every component visible.

    Represents: how well this finding is backed by our sources. NOT a probability
        of being true (see ARCHITECTURE.md section 8).
    Why it exists: an auditable number. For any score we can show the exact
        sources, origins and conflicts that produced it.
    Validation: score in [0, 1]; components stored so the arithmetic can be
        re-checked.
    Why a model: it is rendered to analysts and saved for audit. The breakdown
        must always be present, not optional dict keys.
    """

    finding_id: str
    score: float = Field(ge=0.0, le=1.0)
    label: SupportLabel
    base: float
    corroboration: float
    conflict_penalty: float
    verdict_multiplier: float
    supporting_origins: list[str]
    contradicting_origins: list[str]
    explanation: str  # e.g. "1 tier-A origin, 1 independent tier-B origin, no conflicts"


class OverallScore(Record):
    """The briefing headline: two separate answers, deliberately not combined.

    Support      (score, label): how well the statements we make are backed.
    Completeness (completeness, coverage_ratio): how much of the question we answered.

    Why separate: multiplying them made solid findings look "weakly supported"
    just because one area had no evidence. An analyst or compliance reader should
    see "what we say is well backed" and "here is what we could not cover" as two
    distinct facts.
    """

    score: float = Field(ge=0.0, le=1.0)  # average finding score (support only)
    label: SupportLabel
    coverage_ratio: float = Field(ge=0.0, le=1.0)  # covered 1 / thin 0.5 / gap 0, averaged
    completeness: str  # e.g. "3 of 4 areas answered (2 well covered, 1 thinly); no evidence for 1"
    reasons: list[str]  # plain-English reasons shown next to the label
