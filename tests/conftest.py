"""Shared test fixtures. pytest loads this file automatically before any test.

A fixture defined here is available to every test file by parameter name.
"""

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel


@pytest.fixture
def fake_llm():
    """Factory for a fake LLM: no network, no API key, no cost.

    Usage in a test:
        model, seen = fake_llm(answer1, answer2)
        Planner(model)(...)

    The fake returns the given answers in order (one per request) and records the
    messages it was sent in `seen`, so tests can check what the agent sent.
    Structured output is returned by "calling" the output tool Pydantic AI defines.
    """

    def make(*answers: dict) -> tuple[FunctionModel, list[list[ModelMessage]]]:
        queue, seen = list(answers), []

        def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            seen.append(messages)
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, queue.pop(0))])

        return FunctionModel(respond), seen

    return make
