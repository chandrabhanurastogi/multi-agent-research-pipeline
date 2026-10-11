"""Source quality rules shared by sufficiency.py and confidence.py.

One place decides "how much is this source worth?", so the two policies can
never disagree about it.
"""

from datetime import date

from research_pipeline.domain.research.source import Source, Tier

STALE_AFTER_YEARS = 3

_ONE_TIER_DOWN = {Tier.A: Tier.B, Tier.B: Tier.C, Tier.C: Tier.C}


def is_stale(source: Source, as_of: date) -> bool:
    """Older than STALE_AFTER_YEARS on the run date."""
    age_days = (as_of - source.published).days
    return age_days > STALE_AFTER_YEARS * 365


def effective_tier(source: Source, as_of: date) -> Tier:
    """The tier a source counts as today: its tier, one level lower if stale.

    Example: S11 (tier B, published 2019) counts as tier C in 2026.
    """
    return _ONE_TIER_DOWN[source.tier] if is_stale(source, as_of) else source.tier


def is_credible(source: Source, as_of: date) -> bool:
    """Credible = counts as tier A or B today."""
    return effective_tier(source, as_of) in (Tier.A, Tier.B)
