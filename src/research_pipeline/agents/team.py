"""The four agents as one bundle: what the workflow depends on.

The workflow receives an `Agents` object instead of creating agents itself
(dependency injection). In a real run it gets `build_agents(configured_model())`;
in tests it gets plain fake functions that return prepared AgentResults, so the
workflow's branching can be tested with no LLM and no framework at all.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from pydantic_ai.models import Model

from research_pipeline.agents.planner import Planner
from research_pipeline.agents.researcher import Researcher
from research_pipeline.agents.synthesiser import Synthesiser
from research_pipeline.agents.verifier import Verifier
from research_pipeline.domain.contracts.agent_result import AgentResult
from research_pipeline.domain.contracts.planner_output import PlannerOutput
from research_pipeline.domain.contracts.researcher_output import ResearcherOutput
from research_pipeline.domain.contracts.synthesiser_output import SynthesiserOutput
from research_pipeline.domain.contracts.verifier_output import VerifierOutput
from research_pipeline.domain.research.evidence import Claim
from research_pipeline.domain.research.findings import Draft
from research_pipeline.domain.research.plan import SubQuestion
from research_pipeline.domain.research.source import Source


@dataclass(frozen=True)
class Agents:
    planner: Callable[[str, date], AgentResult[PlannerOutput]]
    researcher: Callable[[SubQuestion, list[Source]], AgentResult[ResearcherOutput]]
    synthesiser: Callable[..., AgentResult[SynthesiserOutput]]
    verifier: Callable[[Draft, list[Claim], dict[str, Source]], AgentResult[VerifierOutput]]


def build_agents(model: str | Model) -> Agents:
    return Agents(
        planner=Planner(model),
        researcher=Researcher(model),
        synthesiser=Synthesiser(model),
        verifier=Verifier(model),
    )
