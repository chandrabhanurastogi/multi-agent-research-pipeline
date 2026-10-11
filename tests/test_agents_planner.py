"""Planner agent tests with a FAKE model (fixture `fake_llm` in conftest.py).

Proves the retry-on-invalid-output behaviour that every agent relies on.
"""

from datetime import date

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import RetryPromptPart

from research_pipeline.agents.planner import Planner

AS_OF = date(2026, 10, 1)


def sub_question(n: int) -> dict:
    return {"question": f"Distinct sub-question number {n}?", "search_terms": ["term"], "rationale": "it matters"}


def plan_json(n_sub_questions: int) -> dict:
    return {
        "interpretation": {"restated_question": "A precise restatement", "scope": "global", "assumptions": []},
        "sub_questions": [sub_question(i) for i in range(1, n_sub_questions + 1)],
    }


def test_valid_plan_is_returned_with_usage(fake_llm):
    model, _ = fake_llm(plan_json(4))
    result = Planner(model)("overview of dry bulk", AS_OF)
    assert len(result.output.sub_questions) == 4
    assert result.requests == 1


def test_query_and_date_are_sent_to_the_llm(fake_llm):
    model, seen = fake_llm(plan_json(3))
    Planner(model)("overview of dry bulk", AS_OF)
    sent = str(seen[0])
    assert "overview of dry bulk" in sent and "2026-10-01" in sent


def test_invalid_output_is_sent_back_and_retried(fake_llm):
    # 1st answer breaks the contract (2 sub-questions, min is 3); 2nd answer is valid.
    model, seen = fake_llm(plan_json(2), plan_json(3))
    result = Planner(model)("overview of dry bulk", AS_OF)

    assert len(result.output.sub_questions) == 3
    assert result.requests == 2
    # The second request carried the validation error back to the "LLM"
    retry_parts = [p for msg in seen[1] for p in getattr(msg, "parts", []) if isinstance(p, RetryPromptPart)]
    assert retry_parts and "at least 3" in str(retry_parts[0].content)


def test_still_invalid_after_retry_raises(fake_llm):
    # OUTPUT_RETRIES = 1: one retry, then the step fails; the workflow decides what to do.
    model, _ = fake_llm(plan_json(2), plan_json(2))
    with pytest.raises(UnexpectedModelBehavior):
        Planner(model)("overview of dry bulk", AS_OF)
