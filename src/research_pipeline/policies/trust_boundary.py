"""Evidence policy: the trust boundary between LLM output and accepted records.

Every LLM output passes through one of these functions before it enters RunState:

    check_claims    Researcher output   -> accepted Claims + RejectedClaims
    check_draft     Synthesiser output  -> Draft with valid references only
    check_verdicts  Verifier output     -> Verdicts that can only REMOVE support

Code checks EXISTENCE (does this quote/ID/source exist?). The Verifier LLM checks
MEANING (does the evidence back the statement?). Neither replaces the other.

Pure functions: no LLM, no I/O, no global state. Problems are returned as
plain-English strings; the workflow records them as Issues.
"""

import re

from research_pipeline.domain.contracts.researcher_output import ExtractedClaim
from research_pipeline.domain.contracts.synthesiser_output import SynthesiserOutput
from research_pipeline.domain.research.evidence import Claim, RejectedClaim
from research_pipeline.domain.research.findings import Draft, Finding, Verdict, VerdictStatus
from research_pipeline.domain.research.source import Source

_TYPOGRAPHIC = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})


def _normalise(text: str) -> str:
    """Make the quote check tolerant of formatting, not of wording.

    Ignores: case, repeated whitespace/newlines, curly vs straight quotes, dashes,
    and punctuation at the very start/end of the quote (LLMs often drop a final ".").
    Still requires the same words in the same order.
    """
    text = " ".join(text.translate(_TYPOGRAPHIC).lower().split())
    return text.strip(" .,;:!?\"'")


# --- Researcher --------------------------------------------------------------


def check_claims(
    sub_question_id: str,
    candidates: list[ExtractedClaim],
    provided: list[Source],
    first_id: int,
) -> tuple[list[Claim], list[RejectedClaim]]:
    """Accept a candidate claim only if its evidence demonstrably exists.

    A candidate is rejected when:
      - its source was not among the documents given to the Researcher for this
        sub-question (even if that document exists elsewhere in the corpus:
        the claim cannot have come from what the agent actually read);
      - its quote is not found in that source's text (invented or altered evidence);
      - it duplicates an already accepted claim (same source, same quote).

    Accepted claims get code-assigned IDs C{first_id}, C{first_id+1}, ...
    """
    by_id = {s.source_id: s for s in provided}
    accepted: list[Claim] = []
    rejected: list[RejectedClaim] = []
    seen: set[tuple[str, str]] = set()

    for c in candidates:
        source = by_id.get(c.source_id)
        key = (c.source_id, _normalise(c.quote))

        if source is None:
            reason = f"{c.source_id} was not provided for this sub-question"
        elif _normalise(c.quote) not in _normalise(source.text):
            reason = f"quote not found in {c.source_id}"
        elif key in seen:
            reason = f"duplicate of an accepted claim from {c.source_id}"
        else:
            seen.add(key)
            accepted.append(
                Claim(
                    id=f"C{first_id + len(accepted)}",
                    sub_question_id=sub_question_id,
                    source_id=c.source_id,
                    statement=c.statement,
                    quote=c.quote,
                )
            )
            continue

        rejected.append(
            RejectedClaim(
                sub_question_id=sub_question_id,
                source_id=c.source_id,
                statement=c.statement,
                quote=c.quote,
                reason=reason,
            )
        )
    return accepted, rejected


# --- Synthesiser -------------------------------------------------------------


def check_draft(output: SynthesiserOutput, claim_ids: set[str]) -> tuple[Draft, list[str]]:
    """Keep only references to claims that exist; assign finding IDs F1, F2, ...

    - Unknown claim IDs are removed from a finding's citations.
    - A finding left with no valid citation is dropped (no uncited statements).
    - A disagreement left with fewer than two valid claims is dropped.

    The returned Draft may have zero findings; the workflow treats that as a
    Synthesiser failure.
    """
    problems: list[str] = []

    findings: list[Finding] = []
    for i, f in enumerate(output.findings, start=1):
        unknown = [cid for cid in f.claim_ids if cid not in claim_ids]
        valid = [cid for cid in dict.fromkeys(f.claim_ids) if cid in claim_ids]  # dedupe, keep order
        if unknown:
            problems.append(f"finding {i} cited unknown claims {unknown}")
        if not valid:
            problems.append(f"finding {i} dropped: no valid citation ({f.statement[:60]!r})")
            continue
        findings.append(Finding(id=f"F{len(findings) + 1}", statement=f.statement, claim_ids=valid))

    disagreements = []
    for d in output.disagreements:
        valid = [cid for cid in dict.fromkeys(d.claim_ids) if cid in claim_ids]
        if len(valid) < 2:
            problems.append(f"disagreement dropped: fewer than two valid claims ({d.description[:60]!r})")
            continue
        disagreements.append(d.model_copy(update={"claim_ids": valid}))

    draft = Draft(
        summary=output.summary,
        findings=findings,
        disagreements=disagreements,
        follow_up_questions=output.follow_up_questions,
    )
    return draft, problems


# --- Verifier ----------------------------------------------------------------


def check_verdicts(
    verdicts: list[Verdict], draft: Draft, claim_ids: set[str]
) -> tuple[list[Verdict], list[str]]:
    """Make verdicts safe to score from. The Verifier may only REMOVE support.

    - Verdicts for unknown findings, and repeat verdicts for the same finding, are dropped.
    - supporting_claim_ids is cut down to claims the finding actually cited.
      (The Verifier cannot invent support the Synthesiser never cited.)
    - contradicting_claim_ids is cut down to claims that exist.
    - A claim listed as both supporting and contradicting is treated as NOT supporting.
    - SUPPORTED/PARTIAL with no supporting claim left is downgraded to UNSUPPORTED.

    Findings with no verdict at all are reported as problems; the workflow treats
    them as unverified.
    """
    cited = {f.id: set(f.claim_ids) for f in draft.findings}
    problems: list[str] = []
    checked: list[Verdict] = []
    done: set[str] = set()

    for v in verdicts:
        if v.finding_id not in cited:
            problems.append(f"verdict for unknown finding {v.finding_id} dropped")
            continue
        if v.finding_id in done:
            problems.append(f"repeat verdict for {v.finding_id} ignored")
            continue
        done.add(v.finding_id)

        contradicting = [cid for cid in dict.fromkeys(v.contradicting_claim_ids) if cid in claim_ids]
        supporting = [
            cid
            for cid in dict.fromkeys(v.supporting_claim_ids)
            if cid in cited[v.finding_id] and cid not in contradicting
        ]
        added = set(v.supporting_claim_ids) - cited[v.finding_id]
        if added:
            problems.append(f"{v.finding_id}: verifier tried to add support {sorted(added)}; removed")

        status = v.status
        if status is not VerdictStatus.UNSUPPORTED and not supporting:
            problems.append(f"{v.finding_id}: marked {status.value} with no valid supporting claim; downgraded")
            status = VerdictStatus.UNSUPPORTED

        checked.append(
            v.model_copy(
                update={"status": status, "supporting_claim_ids": supporting, "contradicting_claim_ids": contradicting}
            )
        )

    for missing in sorted(set(cited) - done):
        problems.append(f"{missing}: no verdict returned")
    return checked, problems
