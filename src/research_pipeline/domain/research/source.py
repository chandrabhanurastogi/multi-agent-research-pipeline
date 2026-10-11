"""Corpus documents and their governed metadata."""

from datetime import date
from enum import StrEnum

from pydantic import Field

from research_pipeline.domain.base import Record


class Tier(StrEnum):
    """Source quality tier, assigned by humans (us), never by the LLM."""

    A = "A"  # regulator, industry body, official statistics
    B = "B"  # broker research, reputable press
    C = "C"  # blogs, forums, anonymous or unverifiable


class Source(Record):
    """One document in the mock research corpus.

    Represents: a document as a search engine or document store would return it,
        plus governed metadata (tier, primary_origin, published).
    Why it exists: tier and origin drive confidence. They must come from trusted
        metadata, not from LLM judgement, so they live on the source itself.
    Validation: ID format; tier is a known value; text not empty; primary_origin
        present (it is the original source of the information, or this
        document's own ID if it is original work).
    Why a model, not a dict: every downstream step relies on these fields being
        present and correctly typed. A dict with a missing "tier" key would only
        fail deep inside the scorer.
    """

    source_id: str = Field(pattern=r"^S\d{2}$")
    title: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    tier: Tier
    primary_origin: str = Field(min_length=1)
    published: date
    text: str = Field(min_length=1)
