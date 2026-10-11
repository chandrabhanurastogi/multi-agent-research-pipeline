"""Sufficiency policy: does each sub-question have "enough" evidence?

"Enough" is a defined, published bar, not a feeling:

    covered  claims from >= 2 credible sources with DIFFERENT primary_origin
    thin     claims from exactly 1 credible origin, or only from non-credible sources
    gap      no accepted claims at all

Counting ORIGINS, not documents: two articles repeating one press release are
one piece of evidence, not two (ARCHITECTURE.md section 13.1).

Pure functions: no LLM, no I/O.
"""

from datetime import date

from research_pipeline.domain.research.evidence import Claim, Coverage
from research_pipeline.domain.research.plan import SubQuestion
from research_pipeline.domain.research.source import Source
from research_pipeline.policies.source_quality import is_credible


def credible_origins(claims: list[Claim], sources: dict[str, Source], as_of: date) -> set[str]:
    """Distinct primary_origins among the credible sources behind these claims."""
    return {
        sources[c.source_id].primary_origin
        for c in claims
        if is_credible(sources[c.source_id], as_of)
    }


def assess_coverage(
    sub_questions: list[SubQuestion],
    claims: list[Claim],
    sources: dict[str, Source],
    as_of: date,
) -> dict[str, Coverage]:
    """Label every sub-question covered / thin / gap."""
    coverage: dict[str, Coverage] = {}
    for sq in sub_questions:
        sq_claims = [c for c in claims if c.sub_question_id == sq.id]
        n_origins = len(credible_origins(sq_claims, sources, as_of))
        if not sq_claims:
            coverage[sq.id] = Coverage.GAP
        elif n_origins >= 2:
            coverage[sq.id] = Coverage.COVERED
        else:
            coverage[sq.id] = Coverage.THIN
    return coverage


def has_credible_evidence(claims: list[Claim], sources: dict[str, Source], as_of: date) -> bool:
    """False -> the workflow short-circuits to an "insufficient evidence" briefing.

    Stricter than "every sub-question is a gap": a run whose only evidence is a
    forum post and a stale report also stops here. We never ask the Synthesiser
    to write a briefing from nothing but weak sources.
    """
    return bool(credible_origins(claims, sources, as_of))
