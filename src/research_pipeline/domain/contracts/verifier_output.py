"""Verifier contract: what the Verifier LLM may return.

Verdict itself lives in research/findings.py because it is also a record kept in
state and used by the scorer.
"""

from pydantic import Field

from research_pipeline.domain.base import LLMOutput
from research_pipeline.domain.research.findings import Verdict


class VerifierOutput(LLMOutput):
    verdicts: list[Verdict] = Field(min_length=1)
