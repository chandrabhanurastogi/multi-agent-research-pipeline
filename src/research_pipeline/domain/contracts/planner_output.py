"""Planner contract: what the Planner LLM may return.

Passed to Pydantic AI as `output_type`. If the answer does not validate, Pydantic AI
sends the error back and the LLM retries. No IDs here: code assigns SQ1..SQ5.
"""

from pydantic import Field, field_validator

from research_pipeline.domain.base import LLMOutput
from research_pipeline.domain.research.plan import Interpretation


class PlannedSubQuestion(LLMOutput):
    # Field descriptions are sent to the LLM inside the JSON schema: they are instructions too.
    question: str = Field(min_length=10, max_length=300, description="One specific, answerable question")
    search_terms: list[str] = Field(
        min_length=1, max_length=8, description="3-6 short keywords and synonyms likely to appear in documents"
    )
    rationale: str = Field(min_length=3, description="One sentence: why this matters for the analyst's question")


class PlannerOutput(LLMOutput):
    """Planner agent output.

    Represents: the interpretation plus 3-5 sub-questions to investigate.
    Why it exists: it bounds the work. The number of sub-questions directly
        controls the number of Researcher calls and therefore cost.
    Validation: 3-5 sub-questions; no duplicates (case-insensitive).
    Why a model: the bounds (3-5) and the duplicate check are enforced on every
        response, and a violation triggers a retry with the error message.
    """

    interpretation: Interpretation
    sub_questions: list[PlannedSubQuestion] = Field(min_length=3, max_length=5)

    @field_validator("sub_questions")
    @classmethod
    def _no_duplicates(cls, v: list[PlannedSubQuestion]) -> list[PlannedSubQuestion]:
        normalised = [sq.question.strip().lower() for sq in v]
        if len(set(normalised)) != len(normalised):
            raise ValueError("sub-questions must be distinct")
        return v
