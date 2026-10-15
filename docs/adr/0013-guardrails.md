# 0013. Guardrails at the gateway where offered, PII masking in the app

- **Status:** Proposed (decide at A9)
- **Date:** 2026-10-15
- **Related:** SEC-8, SEC-9; plan step A9

## Context
Existing controls: documents passed as delimited data, the LLM cannot set IDs, tiers or scores, and the trust boundary rejects quotes not found in sources. Missing: content moderation of inputs and outputs, prompt-injection detection on user input, and PII masking.

## Decision (proposed)
- **Content and injection guardrails at the gateway** if the AI platform team offers them, so policy is central and shared across teams.
- **PII detection and masking in the app with Presidio**, before text reaches the LLM or logs, because what counts as PII is partly domain-specific.
- If the gateway offers no guardrails: evaluate Guardrails AI, NeMo Guardrails and a prompt-injection classifier in A9, scored on the golden set's injection and PII cases.
- The trust boundary stays the primary hallucination control; guardrails do not replace it.

## Alternatives considered
To be compared in A9 on the golden set: Guardrails AI, NeMo Guardrails, cloud provider guardrails (e.g. Bedrock Guardrails, Azure AI Content Safety), a prompt-injection classifier model.

## Consequences
- Depends on what the gateway team provides; confirm during gateway onboarding (Phase B).
