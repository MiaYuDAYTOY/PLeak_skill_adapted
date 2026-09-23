---
name: objection-library
description: >
  Extract every objection buyers raise across your full set of sales calls, rank
  them by how often they come up, capture them in the buyer's own words, and tag
  each to the point in the funnel where it lands. Use when you want the real
  objections instead of the three sales happens to remember, when building or
  refreshing objection handling and enablement, or when you have a stack of call
  recordings and no time to listen through them. Triggers: "what objections are
  we getting," "objection handling," "build a rebuttal doc," "what's blocking
  deals," "sales enablement from calls."
---

# Objection Library

## What this does

Reads all of your sales conversations and returns a ranked library of the
objections buyers actually raise - each one in the buyer's own language, counted
by frequency, and tagged to the stage of the funnel where it shows up. It also
records how reps currently respond and whether that response tends to move the
deal forward.

The point is coverage. Teams usually build objection handling from the handful
of objections that stung most recently. This gives you the full set, weighted by
how common each one really is.

## Why this is a Fable-recommended job

Objections are scattered across many hours of talk. To rank them honestly you
have to hear all of them and count across the whole set, which means holding
every transcript at once. Claude Fable 5 can take the full call library in a
single run and surface patterns no one person sitting through calls would tally.

**If Fable is not available or the budget is spent:** batch it. Run 8-10 calls at
a time, produce a partial objection list per batch, then merge and re-rank the
partial lists in a final pass.

## Evidence to gather first

- Sales and demo call transcripts across the funnel (discovery through
  negotiation)
- Objection notes from reps or deal desk
- Support and onboarding calls, if pre-sale concerns surface there
- Lost-deal notes

Read `.agents/product-marketing-context.md` first if it exists, so objections can
be mapped against your positioning and competitors.

## Process

1. Confirm the call set and window. Report how many calls are included.
2. Read every call. Pull each moment where a buyer raises a concern, hesitation,
   or blocker - stated as a question, a worry, or a flat no.
3. Normalize duplicates: the same underlying objection phrased three ways becomes
   one entry, with the variant phrasings kept as examples.
4. Count how many calls each objection appears in and tag the funnel stage.
5. Capture the current rep response for each and note where a response seems to
   land or fall flat.
6. Produce the library.

## Output format

- **Summary** - calls analyzed, window, top objections by frequency and by
  funnel stage.
- **Objection table** - objection (in buyer language) | funnel stage | number of
  calls | representative quote with source | current response | how well it seems
  to work.
- **Gaps** - objections with no consistent response, or where the current
  response is weak.
- **Recommended handling** - a suggested response for the top objections,
  grounded in what already works in the winning calls.

## The evidence standard

Every objection entry must quote at least one real buyer moment and cite its
source (call name, date, or line). Use the buyer's words, not a tidied-up
paraphrase. If frequency cannot be counted reliably from the material, say so
rather than inventing a number. Recommended responses should be built from
responses that appear to work in your own calls before any that are added from
general practice - and anything added from general practice must be labeled as
such.
