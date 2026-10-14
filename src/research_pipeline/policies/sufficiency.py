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
    origins = set()  # A set automatically ignores duplicates!

    for c in claims:
        # 1. Look up the document that this claim came from
        doc = sources[c.source_id]

        # 2. Check if this document is high quality (Tier A/B) and fresh (< 3 years old)
        if is_credible(doc, as_of):
            # 3. Add the root source name to our set
            origins.add(doc.primary_origin)

    return origins



def assess_coverage(
    sub_questions: list[SubQuestion],
    claims: list[Claim],
    sources: dict[str, Source],
    as_of: date,
) -> dict[str, Coverage]:
    """Label every sub-question covered / thin / gap."""
    coverage: dict[str, Coverage] = {}
    for sq in sub_questions:
        # STEP 1: Filter claims that belong to this sub-question
        sq_claims = [c for c in claims if c.sub_question_id == sq.id]

        # STEP 2: Count how many independent, credible origins back these claims
        n_origins = len(credible_origins(sq_claims, sources, as_of))

        # STEP 3: Assign coverage label based on strict criteria
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
