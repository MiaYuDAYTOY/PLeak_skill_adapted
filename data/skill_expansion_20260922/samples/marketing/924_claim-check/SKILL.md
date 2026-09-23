---
name: claim-check
description: >
  Take every claim in your current messaging and check whether anything in your
  evidence base actually backs it. Reads your positioning and copy against your
  proof material - reviews, case studies, call transcripts, data - and flags the
  claims running on faith. Use before a launch or a website refresh, when
  tightening messaging, or when you want to know which of your claims would
  survive a skeptical buyer or a legal review. Triggers: "can we back this
  claim," "is our messaging supported," "evidence for our claims," "which claims
  are risky," "substantiate our messaging."
---

# Claim Check

## What this does

Pulls every claim out of your live messaging, then goes looking through your
evidence base for something that supports each one. It returns each claim with a
verdict: supported (and by what), thin (some support, not enough), or unsupported
(nothing in the evidence backs it). The unsupported and thin claims are the ones
that get you in trouble - with buyers who probe, with sales who can't prove them,
and with legal who can't sign off.

This is the discipline behind "evidence over vibes." A claim you cannot back is a
liability, however good it sounds.

## Why this is a Fable-recommended job

Checking a claim means searching your whole proof base for support, and doing it
for every claim at once. That needs both your messaging and your entire evidence
corpus held together. Claude Fable 5 can take the claims and the full proof set
in a single run and cross-reference each claim against everything, rather than
you grepping for evidence one line at a time.

**If Fable is not available or the budget is spent:** extract the claim list
first in one pass, then check claims against the evidence in batches by theme
(e.g. all performance claims against the performance evidence). Slower and it can
miss cross-theme support, but the method holds.

## Evidence to gather first

Claims come from:

- Homepage, product pages, pricing page
- Sales deck, one-pagers, battlecards
- Ad and email copy

Proof comes from:

- Customer reviews and testimonials (G2, Capterra, quotes)
- Case studies and reference stories
- Sales call transcripts where customers describe results
- Product data, benchmarks, internal metrics
- Analyst mentions

Read `.agents/product-marketing-context.md` first if it exists.

## Process

1. Extract every claim from the messaging material. A claim is any assertion a
   buyer could dispute - a number, a superiority statement, an outcome promise, a
   category claim.
2. For each claim, search the proof base for support.
3. Assign a verdict: supported, thin, or unsupported, and record the specific
   proof (or its absence).
4. For unsupported and thin claims, note what evidence would be needed to back
   them, or suggest a softer wording the evidence can carry.
5. Flag anything that reads as a regulated or comparative claim that may need
   legal review.
6. Produce the report.

## Output format

- **Summary** - claims checked, split by verdict, the riskiest claims up top.
- **Claim table** - claim (as written) | source surface | verdict | supporting
  proof with source, or "none found" | suggested fix.
- **Fix list** - for each thin or unsupported claim: get evidence, reword, or
  remove.
- **Review flags** - claims that may need legal or compliance sign-off.

## The evidence standard

A claim is only marked "supported" when a specific piece of proof is cited - the
review, case study, transcript line, or dataset, named. "It's probably true" is
not support; if no proof is found, the verdict is "unsupported," full stop. Do
not soften a verdict to be reassuring. Suggested rewordings must be carriable by
the evidence that does exist.
