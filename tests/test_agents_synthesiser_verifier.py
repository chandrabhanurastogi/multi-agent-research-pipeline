"""Synthesiser and Verifier tests with a FAKE model (fixture `fake_llm` in conftest.py).

Focus: what each agent is SHOWN (its prompt) and what it must RETURN (its contract).
"""

import pytest

from research_pipeline.agents.synthesiser import Synthesiser
from research_pipeline.agents.verifier import Verifier
from research_pipeline.domain.research.evidence import Claim, Coverage
from research_pipeline.domain.research.findings import Draft, Finding, Verdict, VerdictStatus
from research_pipeline.domain.research.plan import Interpretation, SubQuestion
from research_pipeline.tools.search import Corpus

INTERP = Interpretation(restated_question="Overview of the dry bulk market", scope="global", assumptions=[])
SQS = [SubQuestion(id="SQ1", question="What is the orderbook?", search_terms=["orderbook"], rationale="supply")]
COVERAGE = {"SQ1": Coverage.THIN}
CLAIMS = [
    Claim(id="C1", sub_question_id="SQ1", source_id="S04", statement="Orderbook is 7% of fleet",
          quote="The orderbook stands at 7% of the fleet"),
    Claim(id="C2", sub_question_id="SQ1", source_id="S05", statement="Orderbook is about 10%",
          quote="an orderbook-to-fleet ratio of roughly 10%"),
]
DRAFT = Draft(
    summary="s", findings=[Finding(id="F1", statement="The orderbook is at a record low", claim_ids=["C1"])],
    disagreements=[], follow_up_questions=["q"],
)
SYNTH_OK = {"summary": "The orderbook is low but estimates differ.", "follow_up_questions": ["Which estimate is right?"],
            "findings": [{"statement": "Estimates range from 7% to 10%", "claim_ids": ["C1", "C2"]}]}


@pytest.fixture(scope="module")
def sources():
    corpus = Corpus.load()
    return {"S04": corpus.get("S04"), "S05": corpus.get("S05")}


# --- Synthesiser -----------------------------------------------------------------


def test_synthesiser_sees_claims_with_tier_date_quote_and_coverage(fake_llm, sources):
    model, seen = fake_llm(SYNTH_OK)
    Synthesiser(model)(INTERP, SQS, COVERAGE, CLAIMS, sources)
    sent = str(seen[0])
    assert "[C1] (S04, Harbourline Shipbrokers, tier B, published 2026-06-05)" in sent
    assert "quote:" in sent and "The orderbook stands at 7% of the fleet" in sent
    assert "SQ1 [thin]" in sent
    assert "REVISION" not in sent  # first draft: no reviewer feedback


def test_revision_shows_previous_findings_and_reviewer_objections(fake_llm, sources):
    model, seen = fake_llm(SYNTH_OK)
    feedback = [Verdict(finding_id="F1", status=VerdictStatus.PARTIAL, supporting_claim_ids=["C1"],
                        reason="record low is not in the quote", suggested_rewrite="Harbourline reports 7%")]
    Synthesiser(model)(INTERP, SQS, COVERAGE, CLAIMS, sources, previous=DRAFT, feedback=feedback)
    sent = str(seen[0])
    assert "REVISION" in sent
    assert "REVIEWER (partial): record low is not in the quote" in sent
    assert "Suggested wording: Harbourline reports 7%" in sent


def test_briefing_without_follow_up_questions_is_retried(fake_llm, sources):
    no_follow_ups = {**SYNTH_OK, "follow_up_questions": []}
    model, _ = fake_llm(no_follow_ups, SYNTH_OK)
    result = Synthesiser(model)(INTERP, SQS, COVERAGE, CLAIMS, sources)
    assert result.requests == 2 and result.output.follow_up_questions == ["Which estimate is right?"]


# --- Verifier --------------------------------------------------------------------


def test_verifier_sees_cited_quotes_and_all_claims(fake_llm, sources):
    model, seen = fake_llm({"verdicts": [{"finding_id": "F1", "status": "partial", "supporting_claim_ids": ["C1"],
                                          "reason": "record low not stated"}]})
    result = Verifier(model)(DRAFT, CLAIMS, sources)
    sent = str(seen[0])
    assert "F1: The orderbook is at a record low" in sent
    assert "All claims (use these to find contradictions)" in sent and "[C2]" in sent  # uncited claim visible
    assert result.output.verdicts[0].status is VerdictStatus.PARTIAL


def test_verifier_cannot_return_an_unknown_status(fake_llm, sources):
    bad = {"verdicts": [{"finding_id": "F1", "status": "probably fine", "reason": "looks ok"}]}
    good = {"verdicts": [{"finding_id": "F1", "status": "supported", "supporting_claim_ids": ["C1"], "reason": "matches"}]}
    model, _ = fake_llm(bad, good)
    assert Verifier(model)(DRAFT, CLAIMS, sources).requests == 2  # enum rejected -> retried
