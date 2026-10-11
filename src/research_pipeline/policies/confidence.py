"""Confidence policy: how well each finding is backed by our sources.

The score is DERIVED from observable evidence, never asserted by an LLM:

    1. supporting claims (only those the Verifier confirmed) -> sources -> primary_origin
       copies of one press release collapse into one origin
    2. each origin counts at its best EFFECTIVE tier (one level lower if stale)
    3. base          = best origin's tier weight            A 0.60 | B 0.45 | C 0.15
    4. corroboration = +0.15 per OTHER credible origin       max +0.30
    5. conflict      = per contradicting origin              A/B -0.25 | C -0.05
                       contradicting = Verifier's list + the other side of any recorded
                       disagreement the finding cites only one side of
                       (an origin that also supports counts as support only)
    6. multiplier    = verdict                               supported 1.0 | partial 0.6
    7. score         = clamp((base + corroboration - conflict) * multiplier, 0, 1)
    8. label         = >= 0.70 Strongly | >= 0.40 Partly | < 0.40 Weakly supported

What a score means: how well OUR sources back the statement under this rule.
What it does NOT mean: a probability of being true. It is not calibrated, and it
knows nothing about evidence outside the corpus. The weights below are POLICY,
to be agreed with analysts and compliance, not statistics.

Pure functions: no LLM, no I/O.
"""

from datetime import date

from research_pipeline.domain.research.evidence import Claim, Coverage
from research_pipeline.domain.research.findings import Draft, Finding, Verdict, VerdictStatus
from research_pipeline.domain.research.scores import FindingScore, OverallScore, SupportLabel
from research_pipeline.domain.research.source import Source, Tier
from research_pipeline.policies.source_quality import effective_tier

# --- Policy constants --------------------------------------------------------

TIER_WEIGHT = {Tier.A: 0.60, Tier.B: 0.45, Tier.C: 0.15}
CORROBORATION_PER_ORIGIN = 0.15
CORROBORATION_MAX = 0.30
CONFLICT_PENALTY = {Tier.A: 0.25, Tier.B: 0.25, Tier.C: 0.05}
VERDICT_MULTIPLIER = {VerdictStatus.SUPPORTED: 1.0, VerdictStatus.PARTIAL: 0.6}
STRONG_AT = 0.70
PARTIAL_AT = 0.40
UNVERIFIED_CAP = 0.39  # no verdict -> can never be better than "Weakly supported"
COVERAGE_WEIGHT = {Coverage.COVERED: 1.0, Coverage.THIN: 0.5, Coverage.GAP: 0.0}

_TIER_RANK = {Tier.A: 0, Tier.B: 1, Tier.C: 2}  # lower = better
_TIER_WORDS = {  # how tiers are described to analysts
    Tier.A: "official or industry body",
    Tier.B: "broker research or established press",
    Tier.C: "blog, forum or outdated report",
}


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def label_for(score: float) -> SupportLabel:
    if score >= STRONG_AT:
        return SupportLabel.STRONG
    if score >= PARTIAL_AT:
        return SupportLabel.PARTIAL
    return SupportLabel.WEAK


def _origin_tiers(claim_ids: list[str], claims: dict[str, Claim], sources: dict[str, Source], as_of: date) -> dict[str, Tier]:
    """{primary_origin: best effective tier} for the sources behind these claims."""
    best: dict[str, Tier] = {}
    for cid in claim_ids:
        source = sources[claims[cid].source_id]
        tier = effective_tier(source, as_of)
        current = best.get(source.primary_origin)
        if current is None or _TIER_RANK[tier] < _TIER_RANK[current]:
            best[source.primary_origin] = tier
    return best


def score_finding(
    finding: Finding,
    verdict: Verdict | None,
    claims: dict[str, Claim],
    sources: dict[str, Source],
    as_of: date,
    disputed_by: list[str] = (),
) -> FindingScore | None:
    """Score one finding. Returns None when the Verifier judged it UNSUPPORTED (excluded).

    verdict=None means the finding was not verified (Verifier failed or skipped):
    its own citations are used as support and the score is capped at Weakly.
    """
    if verdict is not None and verdict.status is VerdictStatus.UNSUPPORTED:
        return None

    supporting_ids = verdict.supporting_claim_ids if verdict else finding.claim_ids
    contradicting_ids = [*(verdict.contradicting_claim_ids if verdict else []), *disputed_by]

    support = _origin_tiers(supporting_ids, claims, sources, as_of)
    conflict = {o: t for o, t in _origin_tiers(contradicting_ids, claims, sources, as_of).items() if o not in support}

    ranked = sorted(support.values(), key=_TIER_RANK.__getitem__)
    base = TIER_WEIGHT[ranked[0]]
    credible_others = sum(1 for t in ranked[1:] if t is not Tier.C)
    corroboration = min(CORROBORATION_PER_ORIGIN * credible_others, CORROBORATION_MAX)
    penalty = sum(CONFLICT_PENALTY[t] for t in conflict.values())
    multiplier = VERDICT_MULTIPLIER[verdict.status] if verdict else 1.0

    score = round(max(0.0, min(1.0, (base + corroboration - penalty) * multiplier)), 2)
    if verdict is None:
        score = min(score, UNVERIFIED_CAP)

    parts = [f"Best source: {_TIER_WORDS[ranked[0]]}"]
    parts.append(
        f"confirmed by {credible_others} other independent source{'s' if credible_others > 1 else ''}"
        if credible_others else "not independently confirmed"
    )
    parts.append(_plural(len(conflict), "source disagrees", "sources disagree") if conflict else "no source disagrees")
    if verdict is None:
        parts.append("NOT verified against the quotes")
    elif verdict.status is VerdictStatus.PARTIAL:
        parts.append("only partly backed by the quoted evidence")

    return FindingScore(
        finding_id=finding.id,
        score=score,
        label=label_for(score),
        base=base,
        corroboration=round(corroboration, 2),
        conflict_penalty=round(penalty, 2),
        verdict_multiplier=multiplier,
        supporting_origins=sorted(support),
        contradicting_origins=sorted(conflict),
        explanation="; ".join(parts) + ".",
    )


def score_findings(
    draft: Draft,
    verdicts: list[Verdict] | None,
    claims: list[Claim],
    sources: dict[str, Source],
    as_of: date,
) -> list[FindingScore]:
    """Score every finding. verdicts=None -> nothing was verified."""
    by_finding = {v.finding_id: v for v in verdicts or []}
    claims_by_id = {c.id: c for c in claims}
    scores = [
        score_finding(f, by_finding.get(f.id), claims_by_id, sources, as_of, disputed_by=_disputed_by(f, draft))
        for f in draft.findings
    ]
    return [s for s in scores if s is not None]


def _disputed_by(finding: Finding, draft: Draft) -> list[str]:
    """Claims on the OTHER side of a recorded disagreement this finding takes one side of.

    Why: "Harbourline reports 7%" is literally true, so the Verifier may not call it
    contradicted, yet Meridian says 10%. Attribution must not hide a dispute.
    A finding that reports both sides cites both claims, so nothing is added.
    Deterministic, and it can only lower a score.
    """
    cited = set(finding.claim_ids)
    other_side: set[str] = set()
    for d in draft.disagreements:
        if cited & set(d.claim_ids):
            other_side |= set(d.claim_ids) - cited
    return sorted(other_side)


def score_overall(finding_scores: list[FindingScore], coverage: dict[str, Coverage]) -> OverallScore:
    """Briefing headline: SUPPORT and COMPLETENESS reported separately.

    Support      = average finding score -> label ("Partly supported by our sources").
    Completeness = how many sub-questions have any evidence ("3 of 4 areas answered").

    They are not multiplied: a gap in one area says nothing about how well the
    findings we do report are backed, and combining them made solid findings
    look weak.
    """
    coverage_ratio = sum(COVERAGE_WEIGHT[c] for c in coverage.values()) / len(coverage) if coverage else 0.0
    score = round(sum(s.score for s in finding_scores) / len(finding_scores), 2) if finding_scores else 0.0

    counts = {c: sum(1 for v in coverage.values() if v is c) for c in Coverage}
    answered = counts[Coverage.COVERED] + counts[Coverage.THIN]
    completeness = (
        f"{answered} of {len(coverage)} areas answered "
        f"({counts[Coverage.COVERED]} well covered, {counts[Coverage.THIN]} thinly)"
    )
    if counts[Coverage.GAP]:
        completeness += f"; no evidence for {counts[Coverage.GAP]}"
    reasons = [f"{counts[Coverage.COVERED]} of {len(coverage)} areas well covered by independent sources"]
    if counts[Coverage.THIN]:
        reasons.append(_plural(counts[Coverage.THIN], "area relies", "areas rely") + " on a single source or weak sources")
    if counts[Coverage.GAP]:
        reasons.append("no evidence found for " + _plural(counts[Coverage.GAP], "area", "areas"))
    disputed = sum(1 for s in finding_scores if s.contradicting_origins)
    if disputed:
        reasons.append("sources disagree on " + _plural(disputed, "finding", "findings"))
    if any("NOT verified" in s.explanation for s in finding_scores):
        reasons.append("findings were not independently verified")

    return OverallScore(
        score=score,
        label=label_for(score),
        coverage_ratio=round(coverage_ratio, 2),
        completeness=completeness,
        reasons=reasons,
    )
