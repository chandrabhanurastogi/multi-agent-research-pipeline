"""Base classes. Two opposite strictness levels, chosen by who creates the object."""

from pydantic import BaseModel, ConfigDict


class Record(BaseModel):
    """Base for internal records the pipeline creates itself.

    frozen=True: a record cannot be changed after creation, so a Claim that passed
    the evidence check cannot later be edited into something that would not pass.
    extra="forbid": an unknown field is a programming error, so fail loudly.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class LLMOutput(BaseModel):
    """Base for models an LLM fills in.

    extra="ignore" (tolerant reader): if the model adds a harmless extra field,
    drop it instead of failing and paying for a retry. Required fields and
    constraints are still enforced.
    """

    model_config = ConfigDict(extra="ignore")
