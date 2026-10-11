"""Search and corpus tests. No LLM involved: these run offline in milliseconds."""

import json

import pytest
from pydantic import ValidationError

from research_pipeline.domain.research.source import Tier
from research_pipeline.tools.search import Corpus


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    return Corpus.load()


def ids(sources) -> set[str]:
    return {s.source_id for s in sources}


def test_corpus_loads_and_validates(corpus):
    assert corpus.get("S01").tier is Tier.A
    assert corpus.get("S99") is None


def test_orderbook_query_finds_all_three_conflicting_figures(corpus):
    # 7% (S04), 10% (S05), 12% stale (S11): the verifier needs all three
    assert {"S04", "S05", "S11"} <= ids(corpus.search("orderbook fleet ratio new ships"))


def test_rates_query_finds_both_sides_of_the_forecast(corpus):
    # S04 says rates firm, S06 says rates fall: missing either hides the disagreement
    assert {"S04", "S06"} <= ids(corpus.search("freight rates outlook forecast"))


def test_press_release_copies_are_both_retrievable(corpus):
    # retrieved separately; the confidence policy (not search) counts them as one origin
    found = corpus.search("Atlas Mining iron ore exports")
    assert {"S07", "S08"} <= ids(found)
    assert corpus.get("S07").primary_origin == corpus.get("S08").primary_origin


def test_unrelated_query_returns_nothing(corpus):
    assert corpus.search("lithium battery recycling") == []


def test_plural_and_singular_match(corpus):
    assert ids(corpus.search("ship")) == ids(corpus.search("ships"))


def test_malformed_corpus_fails_at_load(tmp_path):
    bad = tmp_path / "corpus.json"
    bad.write_text(json.dumps([{"source_id": "S01", "title": "x", "tier": "Z"}]))
    with pytest.raises(ValidationError):
        Corpus.load(bad)
