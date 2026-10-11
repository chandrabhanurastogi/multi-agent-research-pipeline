"""Researcher agent: one sub-question + its documents -> candidate claims with exact quotes.

Input:  one SubQuestion and the documents search returned for it
Output: AgentResult[ResearcherOutput]  (contract: domain/contracts/researcher_output.py)
        The claims are UNTRUSTED: policies/trust_boundary.check_claims decides
        which are accepted.
Not its job: searching, judging truth or source quality, writing the briefing.
"""

from pydantic_ai.models import Model

from research_pipeline.agents.runner import build_agent, run_agent
from research_pipeline.domain.contracts.agent_result import AgentResult
from research_pipeline.domain.contracts.researcher_output import ResearcherOutput
from research_pipeline.domain.research.plan import SubQuestion
from research_pipeline.domain.research.source import Source
from research_pipeline.llm.prompts import RESEARCHER_INSTRUCTIONS, researcher_prompt


class Researcher:
    """Built once per run; called once per sub-question."""

    def __init__(self, model: str | Model) -> None:
        self._agent = build_agent(model, ResearcherOutput, RESEARCHER_INSTRUCTIONS)

    def __call__(self, sub_question: SubQuestion, documents: list[Source]) -> AgentResult[ResearcherOutput]:
        return run_agent(self._agent, researcher_prompt(sub_question.question, documents))
