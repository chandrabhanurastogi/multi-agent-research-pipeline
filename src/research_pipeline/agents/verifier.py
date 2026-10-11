"""Verifier agent: draft + claims -> one verdict per finding.

Input:  the Draft (with code-assigned finding IDs) and all accepted claims + sources.
        It sees the quotes, NOT the Synthesiser's reasoning: an independent check.
Output: AgentResult[VerifierOutput]  (contract: domain/contracts/verifier_output.py)
        Verdicts are UNTRUSTED: policies/trust_boundary.check_verdicts ensures the
        Verifier can only remove support, never add it.
Not its job: rewriting the draft (it may only SUGGEST wording), scoring confidence.
"""

from pydantic_ai.models import Model

from research_pipeline.agents.runner import build_agent, run_agent
from research_pipeline.domain.contracts.agent_result import AgentResult
from research_pipeline.domain.contracts.verifier_output import VerifierOutput
from research_pipeline.domain.research.evidence import Claim
from research_pipeline.domain.research.findings import Draft
from research_pipeline.domain.research.source import Source
from research_pipeline.llm.prompts import VERIFIER_INSTRUCTIONS, verifier_prompt


class Verifier:
    """Built once per run; called once per draft (at most twice: original + revision)."""

    def __init__(self, model: str | Model) -> None:
        self._agent = build_agent(model, VerifierOutput, VERIFIER_INSTRUCTIONS)

    def __call__(self, draft: Draft, claims: list[Claim], sources: dict[str, Source]) -> AgentResult[VerifierOutput]:
        return run_agent(self._agent, verifier_prompt(draft, claims, sources))
