"""Connectivity check: one real, typed LLM call. Run: python scripts/check_llm.py

Proves three things before building anything else:
1. the API key and model name in .env work;
2. Pydantic AI returns a validated Pydantic object (not free text);
3. token usage is reported (we record it in the run trace later).
"""

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from research_pipeline.llm.client import TEMPERATURE, model_name


class Capital(BaseModel):
    country: str
    capital: str
    confidence_note: str = Field(description="One short sentence on how sure you are")


def main() -> None:
    model = model_name()
    agent = Agent(
        model,
        output_type=Capital,
        instructions="Answer factual geography questions.",
        model_settings=ModelSettings(temperature=TEMPERATURE),
    )
    result = agent.run_sync("What is the capital of Australia?")
    usage = result.usage  # a property in pydantic-ai 2.x (a method in older versions)

    print(f"model:  {model}")
    print(f"type:   {type(result.output).__name__}")  # a Capital object, not a string
    print(f"output: {result.output.model_dump()}")
    print(f"tokens: in={usage.input_tokens} out={usage.output_tokens} requests={usage.requests}")


if __name__ == "__main__":
    main()
