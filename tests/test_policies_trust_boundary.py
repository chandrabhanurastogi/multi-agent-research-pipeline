"""Evidence policy tests. Each test is one way an LLM can return untrusted output."""

from datetime import date

import pytest

from research_pipeline.domain.contracts.researcher_output import ExtractedClaim
from research_pipeline.domain.contracts.synthesiser_output import DraftFinding, SynthesiserOutput
from research_pipeline.domain.research.findings import Disagreement, Draft, Finding, Verdict, VerdictStatus
from research_pipeline.domain.research.source import Source, Tier
from research_pipeline.policies.trust_boundary import check_claims, check_draft, check_verdicts


def source(sid: str, text: str) -> Source:
    return Source(
        source_id=sid, title="t", publisher="p", tier=Tier.B, primary_origin=sid, published=date(2026, 1, 1), text=text
    )


S04 = source("S04", "The orderbook stands at 7% of the fleet, the lowest level in over two decades.")
S05 = source("S05", "Our fleet database shows an orderbook-to-fleet ratio of roughly 10%.")


def claim(sid: str, quote: str) -> ExtractedClaim:
    return ExtractedClaim(statement="some fact", source_id=sid, quote=quote)


# --- check_claims ------------------------------------------------------------


def test_exact_quote_is_accepted_with_code_assigned_id():
    accepted, rejected = check_claims("SQ2", [claim("S04", "the orderbook stands at 7% of the fleet")], [S04], first_id=7)
    assert [c.id for c in accepted] == ["C7"]
    assert accepted[0].sub_question_id == "SQ2"
    assert rejected == []


@pytest.mark.parametrize(
    "quote",
    [
        "THE ORDERBOOK STANDS AT 7% OF THE FLEET",  # case
        "The orderbook   stands at\n7% of the fleet",  # whitespace
        "the lowest level in over two decades.",  # trailing punctuation
    ],
)
def test_formatting_differences_are_tolerated(quote):
    accepted, _ = check_claims("SQ2", [claim("S04", quote)], [S04], first_id=1)
    assert len(accepted) == 1


def test_invented_quote_is_rejected():
    accepted, rejected = check_claims("SQ2", [claim("S04", "the orderbook is at a record low")], [S04], first_id=1)
    assert accepted == []
    assert rejected[0].reason == "quote not found in S04"


def test_altered_number_is_rejected():
    _, rejected = check_claims("SQ2", [claim("S04", "the orderbook stands at 9% of the fleet")], [S04], first_id=1)
    assert len(rejected) == 1


def test_source_not_provided_for_this_sub_question_is_rejected():
    # S05 exists in the corpus, but the Researcher was only given S04 for this sub-question
    _, rejected = check_claims("SQ2", [claim("S05", "orderbook-to-fleet ratio of roughly 10%")], [S04], first_id=1)
    assert rejected[0].reason == "S05 was not provided for this sub-question"


def test_duplicate_claim_is_rejected():
    dup = claim("S04", "the orderbook stands at 7% of the fleet")
    accepted, rejected = check_claims("SQ2", [dup, dup], [S04], first_id=1)
    assert len(accepted) == 1 and "duplicate" in rejected[0].reason


# --- check_draft -------------------------------------------------------------


def synth(findings: list[DraftFinding], disagreements: list[Disagreement] = ()) -> SynthesiserOutput:
    return SynthesiserOutput(
        summary="A summary of at least twenty chars.",
        findings=findings,
        disagreements=list(disagreements),
        follow_up_questions=["What should be checked next?"],
    )


def test_valid_draft_gets_finding_ids():
    draft, problems = check_draft(synth([DraftFinding(statement="Orders are low", claim_ids=["C1", "C2"])]), {"C1", "C2"})
    assert [f.id for f in draft.findings] == ["F1"] and problems == []


def test_unknown_citation_is_removed_but_finding_kept():
    draft, problems = check_draft(synth([DraftFinding(statement="Orders are low", claim_ids=["C1", "C99"])]), {"C1"})
    assert draft.findings[0].claim_ids == ["C1"]
    assert "C99" in problems[0]


def test_finding_with_no_valid_citation_is_dropped():
    draft, problems = check_draft(
        synth([DraftFinding(statement="Rates will triple", claim_ids=["C99"]), DraftFinding(statement="Orders are low", claim_ids=["C1"])]),
        {"C1"},
    )
    assert [f.statement for f in draft.findings] == ["Orders are low"]
    assert draft.findings[0].id == "F1"  # IDs stay contiguous after a drop
    assert any("dropped" in p for p in problems)


def test_disagreement_needs_two_valid_claims():
    draft, _ = check_draft(
        synth([DraftFinding(statement="Orders are low", claim_ids=["C1"])], [Disagreement(description="7% vs 10%", claim_ids=["C1", "C99"])]),
        {"C1"},
    )
    assert draft.disagreements == []


# --- check_verdicts ----------------------------------------------------------

DRAFT = Draft(
    summary="s",
    findings=[Finding(id="F1", statement="Orders are low (7-10%)", claim_ids=["C1", "C2"])],
    disagreements=[],
    follow_up_questions=[],
)
ALL_CLAIMS = {"C1", "C2", "C3"}


def verdict(**kw) -> Verdict:
    return Verdict(**{"finding_id": "F1", "status": VerdictStatus.SUPPORTED, "reason": "evidence checked", **kw})


def test_verifier_cannot_add_support_the_finding_never_cited():
    [v], problems = check_verdicts([verdict(supporting_claim_ids=["C1", "C3"])], DRAFT, ALL_CLAIMS)
    assert v.supporting_claim_ids == ["C1"]
    assert "tried to add support" in problems[0]


def test_supported_with_no_valid_support_is_downgraded():
    [v], _ = check_verdicts([verdict(supporting_claim_ids=["C3"])], DRAFT, ALL_CLAIMS)
    assert v.status is VerdictStatus.UNSUPPORTED


def test_claim_both_supporting_and_contradicting_counts_as_not_supporting():
    [v], _ = check_verdicts([verdict(supporting_claim_ids=["C1", "C2"], contradicting_claim_ids=["C2"])], DRAFT, ALL_CLAIMS)
    assert v.supporting_claim_ids == ["C1"] and v.contradicting_claim_ids == ["C2"]


def test_unknown_contradicting_claim_is_removed():
    [v], _ = check_verdicts([verdict(supporting_claim_ids=["C1"], contradicting_claim_ids=["C99"])], DRAFT, ALL_CLAIMS)
    assert v.contradicting_claim_ids == []


def test_verdict_for_unknown_finding_dropped_and_missing_verdict_reported():
    checked, problems = check_verdicts([verdict(finding_id="F9", supporting_claim_ids=["C1"])], DRAFT, ALL_CLAIMS)
    assert checked == []
    assert any("F9" in p for p in problems) and any("F1: no verdict" in p for p in problems)
