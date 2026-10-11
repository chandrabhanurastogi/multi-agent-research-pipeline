"""Confidence tests. The first four are worked examples of the scoring rules on the real corpus."""

from datetime import date

import pytest

from research_pipeline.domain.research.evidence import Claim, Coverage
from research_pipeline.domain.research.findings import Draft, Finding, Verdict, VerdictStatus
from research_pipeline.domain.research.scores import SupportLabel
from research_pipeline.policies.confidence import score_finding, score_findings, score_overall
from research_pipeline.tools.search import Corpus

AS_OF = date(2026, 10, 1)


@pytest.fixture(scope="module")
def sources():
    corpus = Corpus.load()
    return {f"S{i:02d}": corpus.get(f"S{i:02d}") for i in range(1, 13)}


# One accepted claim per corpus document: C01 comes from S01, C11 from S11, etc.
CLAIMS = {
    f"C{i:02d}": Claim(id=f"C{i:02d}", sub_question_id="SQ1", source_id=f"S{i:02d}", statement="fact", quote="quote")
    for i in range(1, 13)
}


def score(sources, supporting, contradicting=(), status=VerdictStatus.SUPPORTED, verified=True):
    finding = Finding(id="F1", statement="a finding", claim_ids=list(supporting))
    verdict = (
        Verdict(finding_id="F1", status=status, supporting_claim_ids=list(supporting),
                contradicting_claim_ids=list(contradicting), reason="checked against quotes")
        if verified else None
    )
    return score_finding(finding, verdict, CLAIMS, sources, AS_OF)


# --- worked examples ------------------------------------------------------------


def test_two_independent_tier_a_sources_is_strong(sources):
    s = score(sources, ["C01", "C02"])  # 0.60 + 0.15
    assert (s.score, s.label) == (0.75, SupportLabel.STRONG)


def test_press_release_copies_get_no_corroboration(sources):
    s = score(sources, ["C07", "C08"])  # 0.45 + 0 (same origin)
    assert (s.score, s.label) == (0.45, SupportLabel.PARTIAL)
    assert s.supporting_origins == ["PR-ATLAS-2026"]


def test_orderbook_with_stale_contradiction(sources):
    s = score(sources, ["C04", "C05"], contradicting=["C11"])  # 0.45 + 0.15 - 0.05 (S11 stale -> C)
    assert (s.score, s.label) == (0.55, SupportLabel.PARTIAL)


def test_forum_post_alone_is_weak(sources):
    s = score(sources, ["C10"])
    assert (s.score, s.label) == (0.15, SupportLabel.WEAK)


# --- individual rules ----------------------------------------------------------


def test_credible_contradiction_costs_more_than_weak_one(sources):
    assert score(sources, ["C01"], contradicting=["C06"]).score == 0.35  # 0.60 - 0.25 (tier B)


def test_partial_verdict_multiplies_by_0_6(sources):
    assert score(sources, ["C01", "C02"], status=VerdictStatus.PARTIAL).score == 0.45  # 0.75 x 0.6


def test_unsupported_finding_is_excluded(sources):
    assert score(sources, ["C01"], status=VerdictStatus.UNSUPPORTED) is None


def test_corroboration_is_capped(sources):
    s = score(sources, ["C01", "C02", "C03", "C04", "C05"])  # 0.60 + min(4 x 0.15, 0.30)
    assert (s.score, s.corroboration) == (0.90, 0.30)


def test_origin_that_supports_and_contradicts_counts_as_support_only(sources):
    s = score(sources, ["C07"], contradicting=["C08"])  # same origin PR-ATLAS-2026
    assert s.conflict_penalty == 0 and s.contradicting_origins == []


def test_unverified_finding_is_capped_at_weak(sources):
    s = score(sources, ["C01", "C02"], verified=False)  # would be 0.75
    assert (s.score, s.label) == (0.39, SupportLabel.WEAK)
    assert "NOT verified" in s.explanation


# --- briefing level --------------------------------------------------------------


def test_score_findings_drops_unsupported(sources):
    draft = Draft(summary="s", findings=[Finding(id="F1", statement="a", claim_ids=["C01"]),
                                         Finding(id="F2", statement="b", claim_ids=["C10"])],
                  disagreements=[], follow_up_questions=[])
    verdicts = [Verdict(finding_id="F1", status=VerdictStatus.SUPPORTED, supporting_claim_ids=["C01"], reason="fine"),
                Verdict(finding_id="F2", status=VerdictStatus.UNSUPPORTED, reason="overstated")]
    assert [s.finding_id for s in score_findings(draft, verdicts, list(CLAIMS.values()), sources, AS_OF)] == ["F1"]


def test_overall_reports_support_and_completeness_separately(sources):
    findings = [score(sources, ["C01", "C02"]), score(sources, ["C07", "C08"])]  # 0.75, 0.45 -> mean 0.60
    coverage = {"SQ1": Coverage.COVERED, "SQ2": Coverage.THIN, "SQ3": Coverage.COVERED, "SQ4": Coverage.GAP}
    overall = score_overall(findings, coverage)

    # support: the average of the findings, NOT dragged down by the gap
    assert (overall.score, overall.label) == (0.60, SupportLabel.PARTIAL)
    # completeness: reported on its own
    assert overall.completeness == "3 of 4 areas answered (2 well covered, 1 thinly); no evidence for 1"
    assert overall.coverage_ratio == 0.62  # (1 + 0.5 + 1 + 0) / 4
    assert "no evidence found for 1 area" in overall.reasons


def test_no_findings_scores_zero(sources):
    overall = score_overall([], {"SQ1": Coverage.GAP})
    assert (overall.score, overall.label) == (0.0, SupportLabel.WEAK)
    assert overall.completeness == "0 of 1 areas answered (0 well covered, 0 thinly); no evidence for 1"


# --- disagreements recorded by the Synthesiser ---------------------------------


def _draft_with_orderbook_dispute(finding_claims: list[str]) -> Draft:
    from research_pipeline.domain.research.findings import Disagreement

    return Draft(
        summary="s",
        findings=[Finding(id="F1", statement="orderbook finding", claim_ids=finding_claims)],
        disagreements=[Disagreement(description="7% (S04) vs 10% (S05)", claim_ids=["C04", "C05"])],
        follow_up_questions=["q"],
    )


def test_one_sided_finding_is_penalised_by_recorded_disagreement(sources):
    # "Harbourline reports 7%" - Verifier says supported, no contradictions, but C05 says 10%
    draft = _draft_with_orderbook_dispute(["C04"])
    verdicts = [Verdict(finding_id="F1", status=VerdictStatus.SUPPORTED, supporting_claim_ids=["C04"], reason="quote matches")]
    [s] = score_findings(draft, verdicts, list(CLAIMS.values()), sources, AS_OF)
    assert (s.score, s.contradicting_origins) == (0.20, ["S05"])  # 0.45 - 0.25


def test_finding_reporting_both_sides_is_not_penalised(sources):
    # "Estimates range from 7% to 10%" cites both sides -> corroborated, not contradicted
    draft = _draft_with_orderbook_dispute(["C04", "C05"])
    verdicts = [Verdict(finding_id="F1", status=VerdictStatus.SUPPORTED, supporting_claim_ids=["C04", "C05"], reason="range ok")]
    [s] = score_findings(draft, verdicts, list(CLAIMS.values()), sources, AS_OF)
    assert (s.score, s.contradicting_origins) == (0.60, [])  # 0.45 + 0.15
