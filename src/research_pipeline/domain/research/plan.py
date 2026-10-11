"""The investigation plan: how the question was understood and broken down."""

from pydantic import Field

from research_pipeline.domain.base import LLMOutput, Record


class Interpretation(LLMOutput):
    """How the Planner understood the question (shown at the top of the briefing).

    Represents: the intent behind the query, made explicit.
    Why it exists: if the system misreads the question, the analyst should see
        that immediately instead of reading a good answer to the wrong question.
    Validation: restated question and scope present; at most 5 assumptions.
    Why a model: it is rendered into the briefing; fixed fields mean fixed layout.
    """

    restated_question: str = Field(min_length=10, description="The question restated precisely, in one sentence")
    scope: str = Field(min_length=3, description="Geography, time horizon, and what is in or out of scope")
    assumptions: list[str] = Field(
        default_factory=list, max_length=5, description="Choices made where the question was ambiguous"
    )


class SubQuestion(Record):
    """A sub-question accepted from the Planner, with a code-assigned ID (SQ1..SQ5)."""

    id: str = Field(pattern=r"^SQ\d+$")
    question: str
    search_terms: list[str]
    rationale: str
