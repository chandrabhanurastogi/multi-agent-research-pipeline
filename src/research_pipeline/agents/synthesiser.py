"""Synthesiser agent: accepted claims -> draft briefing (summary, findings, disagreements, follow-ups).

Input:  interpretation, sub-questions with coverage, accepted claims + their sources;
        on revision also the previous Draft and the Verifier's verdicts
Output: AgentResult[SynthesiserOutput]  (contract: domain/contracts/synthesiser_output.py)
        Citations are UNTRUSTED: policies/trust_boundary.check_draft removes unknown
        claim IDs and assigns finding IDs F1..Fn.
Not its job: finding evidence, checking its own work, scoring confidence.
"""

from pydantic_ai.models import Model

from research_pipeline.agents.runner import build_agent, run_agent
from research_pipeline.domain.contracts.agent_result import AgentResult
from research_pipeline.domain.contracts.synthesiser_output import SynthesiserOutput
from research_pipeline.domain.research.evidence import Claim, Coverage
from research_pipeline.domain.research.findings import Draft, Verdict
from research_pipeline.domain.research.plan import Interpretation, SubQuestion
from research_pipeline.domain.research.source import Source
from research_pipeline.llm.prompts import SYNTHESISER_INSTRUCTIONS, synthesiser_prompt


class Synthesiser:
    """Built once per run; called once, plus once more if the Verifier rejects findings."""

    def __init__(self, model: str | Model) -> None:
        self._agent = build_agent(model, SynthesiserOutput, SYNTHESISER_INSTRUCTIONS)

    def __call__(
        self,
        interpretation: Interpretation,
        sub_questions: list[SubQuestion],
        coverage: dict[str, Coverage],
        claims: list[Claim],
        sources: dict[str, Source],
        previous: Draft | None = None,
        feedback: list[Verdict] | None = None,
    ) -> AgentResult[SynthesiserOutput]:
        prompt = synthesiser_prompt(interpretation, sub_questions, coverage, claims, sources, previous, feedback)
        return run_agent(self._agent, prompt)
