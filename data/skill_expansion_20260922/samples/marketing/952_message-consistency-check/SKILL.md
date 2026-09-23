---
name: message-consistency-check
description: >
  Read every customer-facing surface you ship - website, decks, one-pagers,
  emails, ads, product copy - in one pass and report where your core message
  says different things in different places. Prioritizes the mismatches by how
  visible and how high-stakes the surface is. Use before a launch, after a
  repositioning, when onboarding to a role and auditing what's already out there,
  or when the story feels inconsistent but no one has read all of it side by
  side. Triggers: "is our messaging consistent," "audit our copy," "does our
  website match our deck," "message audit," "we repositioned, what still says the
  old thing."
---

# Message Consistency Check

## What this does

Takes your customer-facing material together and finds the places where your core
message is not telling the same story. It reports where the category you claim,
the primary value you lead with, the audience you speak to, and the proof you
cite differ from one surface to the next - then ranks those mismatches so you fix
the ones that matter first.

No single person usually reads the website, the sales deck, the pricing page, the
nurture emails, and the ad copy in one sitting. That is why messaging fractures
quietly after a repositioning or a fast launch. This job does the reading no one
has time for.

## Why this is a Fable-recommended job

Consistency can only be judged by comparison, which means every surface has to be
in view at the same time. Claude Fable 5 can hold your full set of live copy in a
single run and line it up surface against surface, which is what makes the
mismatches visible.

**If Fable is not available or the budget is spent:** pick one surface as the
reference (usually the current homepage or the approved messaging doc), then
compare each other surface against it one at a time. Slower, and it can miss
mismatches between two non-reference surfaces, but it works.

## Evidence to gather first

- Homepage and key website pages
- Sales deck and pitch deck
- One-pagers, solution briefs, battlecards
- Pricing page
- Email sequences and nurture copy
- Paid and social ad copy
- Product UI copy and onboarding, if relevant

Read `.agents/product-marketing-context.md` first if it exists. If there is an
approved messaging framework, use it as the reference standard everything is
checked against.

## Process

1. Establish the reference. Either the approved messaging framework, or - if
   there isn't one - the current homepage as the de facto source of truth. State
   which you used.
2. For each surface, capture how it renders the core message: category, primary
   value, target audience, top three claims, and proof used.
3. Compare across all surfaces. Log every place a surface diverges from the
   reference or from the others.
4. Rate each mismatch by surface visibility (how many buyers see it) and stakes
   (how central the divergent element is).
5. Produce the report.

## Output format

- **Summary** - surfaces analyzed, reference used, count of mismatches by
  severity.
- **Consistency table** - message element (category / value / audience / claim /
  proof) | what the reference says | where it diverges and how | surface |
  severity.
- **Priority fixes** - the handful of mismatches to fix first, with the specific
  edit for each.
- **Consistency watchlist** - lower-stakes divergences worth cleaning up over
  time.

## The evidence standard

Every mismatch must quote the exact wording from each surface involved and name
the surface. Do not report a mismatch you cannot show with the actual copy. When
two surfaces differ, present both versions rather than deciding which is
"correct" unless the reference framework settles it. Severity ratings should be
explained in one line, not asserted.
