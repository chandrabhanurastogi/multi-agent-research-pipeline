"""Policies: deterministic business rules. No LLM, no I/O, fully unit-tested.

    trust_boundary.py  quote check, reference checks, "verifier can only remove support"
    sufficiency.py   covered / thin / gap per sub-question
    source_quality.py effective tier, staleness, credibility (shared by the two below)
    confidence.py    scoring formula + labels
"""
