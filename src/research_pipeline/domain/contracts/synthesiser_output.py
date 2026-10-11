"""Synthesiser contract: what the Synthesiser LLM may return. No IDs: code assigns F1, F2..."""

from pydantic import Field

from research_pipeline.domain.base import LLMOutput
from research_pipeline.domain.research.findings import Disagreement


class DraftFinding(LLMOutput):
    statement: str = Field(min_length=5)
    claim_ids: list[str] = Field(min_length=1, description="Claim IDs this statement is based on")


class SynthesiserOutput(LLMOutput):
    """Synthesiser agent output: the draft briefing content.

    Represents: prose written only from the claims it was given.
    Why it exists: separates writing from checking and scoring.
    Validation: every finding cites at least one claim (no uncited statements);
        every disagreement involves at least two claims; at least one follow-up
        question (an honest briefing always says what to check next). Whether the cited IDs
        exist is checked by policies/trust_boundary.py.
    Why a model: "every finding must cite something" is a rule. A schema enforces
        it on every response; a prompt instruction alone only asks for it.
    """

    summary: str = Field(min_length=20)
    findings: list[DraftFinding] = Field(min_length=1, max_length=10)
    disagreements: list[Disagreement] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(
        min_length=1, max_length=5, description="What the analyst should investigate next, especially gaps"
    )
