"""Researcher contract: what the Researcher LLM may return for ONE sub-question."""

from pydantic import Field

from research_pipeline.domain.base import LLMOutput


class ExtractedClaim(LLMOutput):
    """One fact as the Researcher LLM returned it, before any checking.

    Represents: an untrusted candidate claim.
    Why it exists separately from research.evidence.Claim: the LLM may invent
        quotes or cite a document it was not given. Keeping "what the LLM said"
        as a separate type from "what we accepted" makes the trust boundary
        visible in the code.
    Validation here: shape only (non-empty statement, quote of sensible length).
        Whether the quote really appears in the source is checked by
        policies/trust_boundary.py, because that needs the source text.
    """

    statement: str = Field(min_length=5, description="The fact in plain words")
    source_id: str = Field(description="ID of the document the quote comes from")
    quote: str = Field(
        min_length=8, max_length=400, description="Exact, verbatim text copied from the document"
    )


class ResearcherOutput(LLMOutput):
    """Researcher agent output for ONE sub-question.

    An empty list is valid: "these documents say nothing relevant" is an honest
    answer, and it becomes a coverage gap rather than an error.
    """

    claims: list[ExtractedClaim] = Field(default_factory=list, max_length=10)
