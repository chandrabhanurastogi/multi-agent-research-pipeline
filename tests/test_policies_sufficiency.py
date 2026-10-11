"""Sufficiency and source-quality tests, using the real mock corpus documents."""

from datetime import date

import pytest

from research_pipeline.domain.research.evidence import Claim, Coverage
from research_pipeline.domain.research.plan import SubQuestion
from research_pipeline.domain.research.source import Tier
from research_pipeline.policies.source_quality import effective_tier, is_stale
from research_pipeline.policies.sufficiency import assess_coverage, has_credible_evidence
from research_pipeline.tools.search import Corpus

AS_OF = date(2026, 10, 1)  # fixed run date so tests don't change meaning over time


@pytest.fixture(scope="module")
def sources():
    corpus = Corpus.load()
    return {sid: corpus.get(sid) for sid in [f"S{i:02d}" for i in range(1, 13)]}


SQ = SubQuestion(id="SQ1", question="What drives demand?", search_terms=["demand"], rationale="core")


def claims_from(*source_ids: str) -> list[Claim]:
    return [
        Claim(id=f"C{i}", sub_question_id="SQ1", source_id=sid, statement="fact", quote="quote")
        for i, sid in enumerate(source_ids, start=1)
    ]


def coverage_of(sources, *source_ids: str) -> Coverage:
    return assess_coverage([SQ], claims_from(*source_ids), sources, AS_OF)["SQ1"]


# --- source quality ----------------------------------------------------------


def test_2019_report_is_stale_and_drops_one_tier(sources):
    assert is_stale(sources["S11"], AS_OF)
    assert effective_tier(sources["S11"], AS_OF) is Tier.C  # B -> C


def test_recent_source_keeps_its_tier(sources):
    assert effective_tier(sources["S01"], AS_OF) is Tier.A


# --- coverage ----------------------------------------------------------------


def test_two_independent_credible_sources_is_covered(sources):
    assert coverage_of(sources, "S01", "S02") is Coverage.COVERED  # two tier-A, different origins


def test_press_release_copies_count_once(sources):
    # S07 and S08 are different documents but share primary_origin PR-ATLAS-2026
    assert coverage_of(sources, "S07", "S08") is Coverage.THIN


def test_single_credible_source_is_thin(sources):
    assert coverage_of(sources, "S03") is Coverage.THIN


def test_only_weak_sources_is_thin(sources):
    assert coverage_of(sources, "S10", "S12") is Coverage.THIN  # forum + blog, both tier C


def test_stale_source_does_not_count_towards_covered(sources):
    assert coverage_of(sources, "S04", "S11") is Coverage.THIN  # S11 is effectively tier C


def test_no_claims_is_gap(sources):
    assert coverage_of(sources) is Coverage.GAP


def test_each_sub_question_assessed_separately(sources):
    sq2 = SubQuestion(id="SQ2", question="What about financing?", search_terms=["finance"], rationale="risk")
    coverage = assess_coverage([SQ, sq2], claims_from("S01", "S02"), sources, AS_OF)
    assert coverage == {"SQ1": Coverage.COVERED, "SQ2": Coverage.GAP}


# --- short-circuit decision --------------------------------------------------


def test_only_weak_or_stale_evidence_is_not_credible(sources):
    assert not has_credible_evidence(claims_from("S10", "S11", "S12"), sources, AS_OF)


def test_one_credible_source_is_enough_to_proceed(sources):
    assert has_credible_evidence(claims_from("S10", "S03"), sources, AS_OF)
