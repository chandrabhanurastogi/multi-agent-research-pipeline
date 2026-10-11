"""Shared plumbing for all agents: build a Pydantic AI Agent, run it, return an AgentResult.

Keeps framework details in one place. The workflow only ever sees AgentResult.
"""

from typing import TypeVar

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.exceptions import FallbackExceptionGroup, ModelAPIError, UnexpectedModelBehavior
from pydantic_ai.models import Model
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.settings import ModelSettings

from research_pipeline.domain.contracts.agent_result import AgentResult
from research_pipeline.llm.client import OUTPUT_RETRIES, TEMPERATURE, fallback_model_names, model_name

OutputT = TypeVar("OutputT", bound=BaseModel)

# Everything that means "this agent call failed". The workflow catches exactly these
# and applies the step's failure policy; anything else is a bug and should crash.
AGENT_ERRORS: tuple[type[BaseException], ...] = (
    ModelAPIError,  # provider error: 503 overloaded, 429 rate limit, 5xx, timeout
    FallbackExceptionGroup,  # every model in the fallback chain failed
    UnexpectedModelBehavior,  # output still invalid after OUTPUT_RETRIES
)


def configured_model() -> str | Model:
    """The model every agent uses in a real run, built from .env.

    With LLM_FALLBACK_MODEL set, returns a FallbackModel: if a model fails with
    a provider error (503 overloaded, 429 rate limit, ...), the same request is
    sent to the next model in the chain. Validation failures do NOT trigger
    fallback; they are handled by output retries.
    """
    primary, fallbacks = model_name(), fallback_model_names()
    return FallbackModel(primary, *fallbacks) if fallbacks else primary


def build_agent(model: str | Model, output_type: type[OutputT], instructions: str) -> Agent[None, OutputT]:
    """One configured agent.

    output_type  -> Pydantic AI sends its JSON schema to the LLM and validates the answer.
    retries      -> if validation fails, the error is sent back and the LLM tries again
                    (OUTPUT_RETRIES times); after that UnexpectedModelBehavior is raised.
    model        -> a model string from .env in real runs, or a fake model in tests.
    """
    return Agent(
        model,
        output_type=output_type,
        instructions=instructions,
        model_settings=ModelSettings(temperature=TEMPERATURE),
        retries={"output": OUTPUT_RETRIES},
    )


def run_agent(agent: Agent[None, OutputT], prompt: str) -> AgentResult[OutputT]:
    """Run synchronously and translate the framework result into our own type.

    Errors are NOT caught here: ModelHTTPError (provider down, rate limit) and
    UnexpectedModelBehavior (still invalid after retries) propagate to the
    workflow, which applies each step's failure policy (ARCHITECTURE.md section 10).
    """
    result = agent.run_sync(prompt)
    usage = result.usage
    return AgentResult[OutputT](
        output=result.output,
        input_tokens=usage.input_tokens or 0,
        output_tokens=usage.output_tokens or 0,
        requests=max(usage.requests, 1),
        model=result.response.model_name or "unknown",
        fallback_used=bool(result.response.failed_attempts),  # FallbackModel moved past failed models
    )
