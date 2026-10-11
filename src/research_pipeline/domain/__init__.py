"""Domain: every type in the pipeline. Imports nothing from outside domain/.

    base.py      Record (strict, code-created) and LLMOutput (tolerant, LLM-filled)
    research/    trusted business records
                   Source   = a document in the corpus
                   Claim    = one fact from one Source, carrying its evidence (exact quote)
                   Finding  = a briefing statement written from Claims
                   Verdict  = the Verifier's judgement on one Finding
                   Score    = how well a Finding is backed by sources (computed by code)
    contracts/   what each LLM agent may return (untrusted until policies/ check it)
    state/       RunState: everything one run produced (saved as run.json)
    output/      Briefing: what the analyst reads
"""
