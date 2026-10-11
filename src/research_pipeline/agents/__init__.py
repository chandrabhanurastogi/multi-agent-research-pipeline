"""Agents: the four LLM-backed steps. The ONLY package that imports pydantic_ai.

    runner.py        shared: build_agent(), run_agent() -> AgentResult
    planner.py       query -> PlannerOutput
    researcher.py    one sub-question + its documents -> ResearcherOutput
    synthesiser.py   claims -> SynthesiserOutput
    verifier.py      draft + claims -> VerifierOutput

Output shapes live in domain/contracts/.
"""
