---
name: customer-language-bank
description: >
  Read hundreds of reviews, support tickets, and call snippets in one pass and
  return the exact words and themes buyers use - then map that language against
  your current messaging so you can see where you're talking past them. Use when
  refreshing messaging, writing copy that should sound like the market rather than
  the boardroom, building personas from real voice-of-customer, or when you want
  the phrases customers actually say instead of the ones the team assumes.
  Triggers: "voice of customer," "how do customers describe us," "mine our
  reviews," "what words do buyers use," "make the copy sound like our customers."
---

# Customer Language Bank

## What this does

Reads your voice-of-customer material in bulk and returns the language buyers
actually use - the words for their problem, the phrases they use for the outcome
they want, the terms they use for you and for alternatives. It groups this into
themes ranked by how often each shows up, then holds it up against your current
messaging to show where your words and their words have parted ways.

Copy written in the team's internal language quietly loses buyers who describe
their world differently. This gives you their vocabulary, weighted by frequency,
so the messaging can meet them where they are.

## Why this is a Fable-recommended job

The signal is in the volume - a phrase matters because many customers use it, and
you only see that by reading a lot of them together. Claude Fable 5 can take
hundreds of reviews, tickets, and snippets in a single run and rank the recurring
language, which a sample of a dozen would miss.

**If Fable is not available or the budget is spent:** run in batches of a few
hundred items, produce a themed phrase list per batch, then merge and re-rank the
lists in a final pass.

## Evidence to gather first

- Product reviews (G2, Capterra, app stores, Trustpilot)
- Support tickets and chat logs
- Sales and onboarding call snippets where customers describe their problem or
  results
- Community posts, survey free-text, churn and cancellation reasons
- Social mentions, if available

Read `.agents/product-marketing-context.md` first if it exists, so the language
can be checked against your positioning and personas.

## Process

1. Confirm the sources and roughly how many items are included. The report will
   state the volume.
2. Read all of it. Pull the recurring language for: the problem, the trigger to
   look for a solution, the desired outcome, how they describe your product, and
   how they describe alternatives.
3. Cluster into themes and count frequency. Keep the raw phrasings as examples.
4. Compare the top themes against your current messaging. Note where you use a
   different word than the market does for the same thing.
5. Produce the language bank.

## Output format

- **Summary** - items analyzed, sources, the dominant themes.
- **Language table** - theme | what buyers say (real phrases with source) | how
  often it appears | the word your messaging currently uses | gap.
- **Swap list** - specific places your copy could adopt the buyer's word.
- **Persona signals** - differences in language by segment or role, if the
  material supports splitting them out.

## The evidence standard

Every phrase in the bank must be a real quote with its source noted (review,
ticket, call), not a paraphrase or an invented "customers say" line. Frequency
counts must come from the material; if you can only estimate, label it an
estimate. Do not clean up buyer language into marketing language - the unpolished
wording is the whole point.
