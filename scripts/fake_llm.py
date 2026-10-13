"""A fake LLM for the try_* scripts: run and debug them with no API key, no network, no quota.

    LLM_MODEL=fake python scripts/try_workflow.py

Every agent, the trust boundary, the policies and the workflow run for real; only the
model's answer is made up. The answers are deterministic and look like a well-behaved
model, with two deliberate mistakes so the checking paths have something to do:

    Researcher   quotes the first sentence of each document verbatim (accepted), plus one
                 paraphrased "quote" per call (rejected by the trust boundary)
    Synthesiser  one finding per claim, plus one overreaching finding ("... therefore ...")
    Verifier     marks the overreaching finding PARTIAL, so the single revision runs;
                 the revised draft drops it

Same technique as the `fake_llm` fixture in tests/conftest.py: a Pydantic AI FunctionModel
that answers by "calling" the output tool, so validation and retries work as with a real model.
"""

import os
import re

from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel

from research_pipeline.agents import runner
from research_pipeline.llm.client import fallback_model_names, model_name


def use_fake() -> bool:
    return os.getenv("LLM_MODEL", "").strip().lower() == "fake"


def configured_model() -> str | Model:
    """Drop-in for runner.configured_model(): the fake when LLM_MODEL=fake, else the real model."""
    return FunctionModel(_respond, model_name="fake") if use_fake() else runner.configured_model()


def model_label() -> str:
    return "fake" if use_fake() else " -> ".join([model_name(), *fallback_model_names()])


# --- One answer per agent, chosen by the output schema it asks for ----------------


def _respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    tool = info.output_tools[0]
    fields = set(tool.parameters_json_schema.get("properties", {}))
    prompt = _last_prompt(messages)
    if "sub_questions" in fields:
        args = _plan(prompt)
    elif "claims" in fields:
        args = _research(prompt)
    elif "findings" in fields:
        args = _synthesise(prompt)
    elif "verdicts" in fields:
        args = _verify(prompt)
    else:
        raise ValueError(f"fake LLM: no answer for output fields {sorted(fields)}")
    return ModelResponse(parts=[ToolCallPart(tool.name, args)], model_name="fake")


def _last_prompt(messages: list[ModelMessage]) -> str:
    parts = [p for m in messages for p in getattr(m, "parts", []) if isinstance(p, UserPromptPart)]
    return str(parts[-1].content) if parts else ""


def _plan(prompt: str) -> dict:
    query = prompt.split("Analyst question:\n", 1)[-1].strip()
    sub_questions = [
        ("What drives iron ore and coal demand for dry bulk shipping?", ["iron ore", "coal", "China", "imports", "demand"]),
        ("How large is the orderbook relative to the existing fleet?", ["orderbook", "fleet", "deliveries", "newbuild"]),
        ("How do emissions rules affect fleet speed and supply?", ["emissions", "EEXI", "CII", "speed", "regulation"]),
        ("What do analysts expect for freight rates?", ["freight rates", "forecast", "Capesize", "outlook"]),
    ]
    return {
        "interpretation": {
            "restated_question": f"Fake model's reading of: {query}",
            "scope": "Global dry bulk shipping, current market",
            "assumptions": ["Answered from the demo corpus only (fake LLM)."],
        },
        "sub_questions": [{"question": q, "search_terms": t, "rationale": "A main driver of the market."}
                          for q, t in sub_questions],
    }


_DOCUMENT = re.compile(r'<document id="([^"]+)"[^>]*>\n(.*?)\n</document>', re.S)


def _research(prompt: str) -> dict:
    claims = []
    docs = _DOCUMENT.findall(prompt)
    for source_id, text in docs[:3]:
        sentence = re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0]
        claims.append({"statement": sentence, "source_id": source_id, "quote": sentence})
    if docs:  # a paraphrase, not a quote: the trust boundary must reject it
        source_id, _ = docs[0]
        claims.append({"statement": "The market outlook is described as very strong.", "source_id": source_id,
                       "quote": "the outlook is extremely strong this year"})
    return {"claims": claims}


_CLAIM = re.compile(r"^\[(C\d+)\] \([^)]*\) (.*)$", re.M)


def _synthesise(prompt: str) -> dict:
    claims = _CLAIM.findall(prompt)[:6]
    findings = [{"statement": statement, "claim_ids": [cid]} for cid, statement in claims]
    revising = "\nREVISION." in prompt
    if len(claims) >= 2 and not revising:  # overreach: links two claims with a cause no quote states
        findings.append({"statement": f"{claims[0][1].rstrip('.')}, therefore {claims[1][1][0].lower()}{claims[1][1][1:]}",
                         "claim_ids": [claims[0][0], claims[1][0]]})
    return {
        "summary": "The fake model's summary: the briefing below repeats the accepted claims, one finding each.",
        "findings": findings or [{"statement": "No claims were provided.", "claim_ids": ["C1"]}],
        "disagreements": [],
        "follow_up_questions": ["Which sub-questions had thin or no evidence, and where could that be found?"],
    }


_FINDING = re.compile(r"^(F\d+): (.*)\n  cites:\n((?:    \[C\d+\].*\n?)+)", re.M)


def _verify(prompt: str) -> dict:
    verdicts = []
    for finding_id, statement, cites in _FINDING.findall(prompt):
        claim_ids = re.findall(r"\[(C\d+)\]", cites)
        if "therefore" in statement:
            verdicts.append({"finding_id": finding_id, "status": "partial", "supporting_claim_ids": claim_ids[:1],
                             "contradicting_claim_ids": [],
                             "reason": "The quotes do not state that one causes the other.",
                             "suggested_rewrite": "Report the two facts separately, without 'therefore'."})
        else:
            verdicts.append({"finding_id": finding_id, "status": "supported", "supporting_claim_ids": claim_ids,
                             "contradicting_claim_ids": [], "reason": "The quote states this directly."})
    return {"verdicts": verdicts}
