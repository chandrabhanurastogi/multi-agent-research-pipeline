"""Fake agents for workflow and briefing tests: plain functions, no LLM, no Pydantic AI.

Importable from any test as `from fakes import ...` (pytest puts tests/ on sys.path).
"""

from pydantic_ai.exceptions import ModelHTTPError

from research_pipeline.agents.team import Agents
from research_pipeline.domain.contracts.agent_result import AgentResult
from research_pipeline.domain.contracts.planner_output import PlannedSubQuestion, PlannerOutput
from research_pipeline.domain.contracts.researcher_output import ExtractedClaim, ResearcherOutput
from research_pipeline.domain.contracts.synthesiser_output import DraftFinding, SynthesiserOutput
from research_pipeline.domain.contracts.verifier_output import VerifierOutput
from research_pipeline.domain.research.findings import Verdict, VerdictStatus
from research_pipeline.domain.research.plan import Interpretation

QUERY = "Give me an overview of the dry bulk shipping market"


def ok(output) -> AgentResult:
    return AgentResult(output=output, input_tokens=10, output_tokens=5, requests=1, model="fake")


def provider_down(*_, **__):
    raise ModelHTTPError(503, "fake-model", {"error": "overloaded"})


# --- Fake agents: behave like a well-functioning LLM --------------------------------


def fake_planner(query, as_of):
    sqs = [("What drives iron ore demand from China?", ["China", "iron ore", "imports"]),
           ("What is the orderbook relative to the fleet?", ["orderbook", "fleet", "deliveries"])]
    return ok(PlannerOutput(
        interpretation=Interpretation(restated_question="Overview of dry bulk shipping", scope="global"),
        sub_questions=[PlannedSubQuestion(question=q, search_terms=t, rationale="matters") for q, t in sqs]
        + [PlannedSubQuestion(question="What are emissions rules doing to fleet speed?",
                              search_terms=["EEXI", "CII", "speed"], rationale="matters")],
    ))


def fake_researcher(sub_question, docs):
    # Quote the first sentence of each document verbatim: always passes the evidence check
    return ok(ResearcherOutput(claims=[
        ExtractedClaim(statement=f"Fact from {d.source_id}", source_id=d.source_id, quote=d.text.split(". ")[0])
        for d in docs[:2]
    ]))


def fake_synthesiser(interpretation, sub_questions, coverage, claims, sources, previous=None, feedback=None):
    return ok(SynthesiserOutput(
        summary="A summary of the dry bulk market for the analyst.",
        findings=[DraftFinding(statement=f"Finding based on {c.id}", claim_ids=[c.id]) for c in claims[:3]],
        follow_up_questions=["What should be checked next?"],
    ))


def verifier_saying(status):
    def verify(draft, claims, sources):
        return ok(VerifierOutput(verdicts=[
            Verdict(finding_id=f.id, status=status, supporting_claim_ids=f.claim_ids, reason="checked quotes")
            for f in draft.findings
        ]))
    return verify


def agents(**overrides) -> Agents:
    base = dict(planner=fake_planner, researcher=fake_researcher, synthesiser=fake_synthesiser,
                verifier=verifier_saying(VerdictStatus.SUPPORTED))
    return Agents(**{**base, **overrides})


