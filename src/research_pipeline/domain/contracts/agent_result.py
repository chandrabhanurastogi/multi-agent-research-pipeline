"""What every agent call returns to the workflow: the validated output plus its cost."""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from research_pipeline.domain.base import Record

OutputT = TypeVar("OutputT", bound=BaseModel)


class AgentResult(Record, Generic[OutputT]):
    """Validated agent output + usage, with no framework types.

    Represents: one completed agent call.
    Why it exists: the workflow needs token counts and retry counts for the trace,
        but must not depend on Pydantic AI's result objects. Agents translate
        their framework result into this, so swapping the framework only touches agents/.
    Validation: output is already validated against its contract (e.g. PlannerOutput);
        counts are non-negative.
    requests > 1 means the LLM's first answer failed validation and it retried.
    model records which model answered: with a fallback chain it may not be the primary.
    """

    output: OutputT
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    requests: int = Field(ge=1)
    model: str = "unknown"  # the model that actually answered (may be a fallback model)
    fallback_used: bool = False  # True if earlier models in the fallback chain failed first
