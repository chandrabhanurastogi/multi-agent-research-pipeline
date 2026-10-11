"""Planner agent: analyst question -> interpretation + 3-5 sub-questions.

Input:  the query (and the run date, so "current" has a meaning)
Output: AgentResult[PlannerOutput]  (contract: domain/contracts/planner_output.py)
Not its job: searching, answering, assigning IDs (the workflow assigns SQ1..SQn).
"""

from datetime import date

from pydantic_ai.models import Model

from research_pipeline.agents.runner import build_agent, run_agent
from research_pipeline.domain.contracts.agent_result import AgentResult
from research_pipeline.domain.contracts.planner_output import PlannerOutput
from research_pipeline.llm.prompts import PLANNER_INSTRUCTIONS, planner_prompt


class Planner:
    """Built once per run; called once per run.

    A class (not a bare function) so the configured Pydantic AI agent is created
    once and the model can be injected: a real model string in production, a
    fake model in tests.
    """

    def __init__(self, model: str | Model) -> None:
        self._agent = build_agent(model, PlannerOutput, PLANNER_INSTRUCTIONS)

    def __call__(self, query: str, as_of: date) -> AgentResult[PlannerOutput]:
        return run_agent(self._agent, planner_prompt(query, as_of))
