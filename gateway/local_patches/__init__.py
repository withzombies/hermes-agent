"""Local fork patches over NousResearch/hermes-agent upstream.

Everything specific to *our* deployment lives in this package so that the
upstream-owned files carry only a single-line call-in (one import + one call).
This keeps the rebase-conflict surface near-zero: a brand-new file never
conflicts, and a one-line hook almost never does.

See CLAUDE.md ("Two copies of this repo") and the memory note
``fork-patches-single-line-hooks`` for the rationale.
"""
