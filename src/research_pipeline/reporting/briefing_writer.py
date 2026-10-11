"""RunState -> Briefing -> markdown. Everything the analyst reads is produced here, by code.

Two steps, on purpose:
    build_briefing(state)      decides WHAT the analyst sees (selection, wording, ordering)
    render_markdown(briefing)  decides HOW it looks (markdown today; HTML or an API later)

The layout is fixed: the same sections in the same order on every run, even when
a section is empty ("None found"), so analysts learn where to look.
"""

from datetime import datetime

from research_pipeline.domain.output.briefing import Briefing, BriefingFinding, RunStatus, SourceRef
from research_pipeline.domain.research.evidence import Coverage
from research_pipeline.domain.research.findings import VerdictStatus
from research_pipeline.domain.research.source import Source
from research_pipeline.domain.state.workflow_state import RunState, Severity

_NO_BRIEFING_SUMMARY = {
    RunStatus.INSUFFICIENT_EVIDENCE: (
        "We could not find credible sources (official, industry or established research) on this question, "
        "so no findings are reported. See 'What we could not establish' and the follow-up questions."
    ),
    RunStatus.FAILED: (
        "The briefing could not be produced because a step of the process failed. "
        "Nothing below should be relied on; see 'Needs human review'."
    ),
}


def _ref(s: Source) -> SourceRef:
    return SourceRef(source_id=s.source_id, title=s.title, publisher=s.publisher, tier=s.tier, published=s.published)


def build_briefing(state: RunState) -> Briefing:
    draft, sources = state.draft, state.documents
    claims = {c.id: c for c in state.claims}
    verdicts = {v.finding_id: v for v in state.verdicts}
    scored = {s.finding_id: s for s in state.finding_scores}

    key_findings, unverified, cited_source_ids = [], [], set()
    for f in draft.findings if draft else []:
        score = scored.get(f.id)
        if score is None:  # judged unsupported by the Verifier
            unverified.append(f.statement)
            continue
        verdict = verdicts.get(f.id)
        support_ids = verdict.supporting_claim_ids if verdict and verdict.status is not VerdictStatus.UNSUPPORTED else f.claim_ids
        source_ids = list(dict.fromkeys(claims[cid].source_id for cid in support_ids))
        cited_source_ids.update(source_ids)
        key_findings.append(BriefingFinding(
            statement=f.statement, support=score.label, score=score.score, explanation=score.explanation,
            sources=[_ref(sources[sid]) for sid in source_ids],
        ))

    for d in draft.disagreements if draft else []:
        cited_source_ids.update(claims[cid].source_id for cid in d.claim_ids)

    gaps = [sq.question for sq in state.sub_questions if state.coverage.get(sq.id) is Coverage.GAP]
    follow_ups = list(draft.follow_up_questions) if draft else [f"Find sources that answer: {g}" for g in gaps]

    return Briefing(
        run_id=state.run_id,
        generated_at=datetime.now(),
        query=state.query,
        status=state.status,
        verified=state.verified,
        interpretation=state.interpretation,
        overall=state.overall,
        summary=draft.summary if draft and state.status is not RunStatus.FAILED else _NO_BRIEFING_SUMMARY.get(state.status, ""),
        key_findings=key_findings,
        disagreements=[d.description for d in draft.disagreements] if draft else [],
        gaps=gaps,
        unverified_claims=unverified,
        follow_up_questions=follow_ups,
        review_required=state.review_required,
        review_reasons=[i.message for i in state.issues if i.severity is Severity.REVIEW],
        notes=[i.message for i in state.issues if i.severity is Severity.WARNING],
        sources=sorted((_ref(sources[sid]) for sid in cited_source_ids), key=lambda r: r.source_id),
        model_name=state.model_name,
        models_used=sorted({s.model for s in state.trace if s.model}),
        prompt_version=state.prompt_version,
    )


# --- Markdown ------------------------------------------------------------------------


def _bullets(items: list[str], empty: str = "None.") -> list[str]:
    return [f"- {i}" for i in items] if items else [f"_{empty}_"]


def render_markdown(b: Briefing) -> str:
    out = [f"# Research briefing", "", f"**Question:** {b.query}", "",
           f"_Run {b.run_id} · {b.generated_at:%d %b %Y %H:%M} · status: {b.status.value.replace('_', ' ')}_", ""]

    if b.review_required:
        out += ["> **⚠ Needs human review before use.**"] + [f"> - {r}" for r in b.review_reasons] + [""]
    if b.key_findings and not b.verified:
        out += ["> **⚠ NOT VERIFIED.** The independent check of this briefing failed. "
                "Every finding is shown as weakly supported.", ""]

    if b.interpretation:
        i = b.interpretation
        out += ["## How we read your question", "", i.restated_question, "", f"**Scope:** {i.scope}", ""]
        if i.assumptions:
            out += ["**Assumptions we made:**"] + _bullets(i.assumptions) + [""]

    out += ["## Summary", "", b.summary or "_No summary._", ""]

    out += ["## Overall assessment", ""]
    if b.overall:
        out += [f"- **Support:** {b.overall.label.value} (score {b.overall.score:.2f} of 1)",
                f"- **Completeness:** {b.overall.completeness}"] + [f"- {r}" for r in b.overall.reasons] + [""]
    else:
        out += ["_No assessment: no findings were produced._", ""]

    out += ["## Key findings", ""]
    if b.key_findings:
        for n, f in enumerate(b.key_findings, start=1):
            refs = "; ".join(f"{s.title} ({s.publisher}, {s.published:%b %Y})" for s in f.sources)
            out += [f"{n}. {f.statement}",
                    f"   - **{f.support.value}** (score {f.score:.2f}). {f.explanation}",
                    f"   - Sources: {refs}", ""]
    else:
        out += ["_None._", ""]

    out += ["## Where sources disagree", ""] + _bullets(b.disagreements, "No disagreements found among the sources used.") + [""]
    out += ["## What we could not establish", ""] + _bullets(b.gaps, "Every part of the question had some evidence.") + [""]
    out += ["## Statements we could not verify", "",
            "_These were drafted but not backed by the quoted sources, so they are excluded from the findings above._", ""] \
        + _bullets(b.unverified_claims) + [""]
    out += ["## Suggested follow-up questions", ""] + _bullets(b.follow_up_questions) + [""]
    if b.notes:
        out += ["## Notes", ""] + _bullets(b.notes) + [""]

    out += ["## Sources", "", "| # | Title | Publisher | Type | Published |", "|---|---|---|---|---|"]
    tier_words = {"A": "Official / industry body", "B": "Broker research / press", "C": "Blog / forum (low quality)"}
    out += [f"| {s.source_id} | {s.title} | {s.publisher} | {tier_words[s.tier.value]} | {s.published:%b %Y} |"
            for s in b.sources] or ["| | _none_ | | | |"]

    out += ["", "## About this briefing", "",
            "- Findings are written by an AI model **only from the sources listed above**, then checked by a "
            "second, independent AI review against the exact quoted text.",
            "- **Support levels are calculated by fixed rules, not by the AI:** they reflect the type of source, "
            "whether independent sources agree, and whether any source disagrees.",
            "- A support level is **not a probability that a statement is true**. It says how well our sources "
            "back it. The sources themselves can be wrong, and evidence outside this collection is not considered.",
            f"- Answered by: {', '.join(b.models_used) or 'no AI model'} (configured: {b.model_name}; "
            f"prompt version {b.prompt_version}). Full audit trail: `run.json` in the same folder.", ""]
    return "\n".join(out)
