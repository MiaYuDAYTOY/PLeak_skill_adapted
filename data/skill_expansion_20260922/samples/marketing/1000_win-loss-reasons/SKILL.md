---
name: win-loss-reasons
description: >
  Synthesize why you win and lose deals from your full set of sales call
  transcripts, deal notes, and CRM close reasons at once. Separates what buyers
  said out loud from what the pattern of evidence actually shows, and ties every
  finding back to the calls behind it. Use when you have a pile of win/loss
  material nobody has had time to read across, when sales keeps losing to the
  same competitor and no one can explain why, or when you need win/loss findings
  you can defend in front of leadership. Triggers: "why are we losing deals,"
  "win/loss analysis," "read all these call transcripts," "what's the real
  reason we lost," "win rate against [competitor]."
---

# Win & Loss Reasons

## What this does

Reads your entire body of deal evidence in one pass and reports the real reasons
you win and lose, ranked by how often each reason actually shows up - not by how
loud it was in the last deal anyone remembers.

The output separates two things that usually get blurred together:

- **What buyers said** - the reason the buyer or rep named for the deal ("too
  expensive," "went with a competitor").
- **What the pattern shows** - what many deals read together reveal was really
  going on (e.g. price was named, but the transcripts show the loss tracked to a
  missing integration raised in the second call).

What buyers said is where teams stop. What the pattern shows is where the useful
work is. This skill is built to get you to the second one.

## Why this is a Fable-recommended job

Real win/loss lives across dozens of long transcripts. The value only appears
when you can hold all of them at once and compare across the set - a reason that
shows up in one deal is an anecdote, the same reason across nine deals is a
finding. Claude Fable 5 can hold that whole evidence base in a single run and
cross-reference it, which is exactly what this needs.

**If Fable is not available or the budget is spent:** run on your everyday model
in batches. Feed 8-10 transcripts per batch, produce a partial reason table for
each batch using the format below, then paste those partial tables back in and
ask for a merged, de-duplicated final table. You lose some cross-deal nuance but
keep the method.

## Evidence to gather first

Point the skill at as much of this as you have. More material makes the ranking
more trustworthy.

- Sales call and demo transcripts (Gong, Fireflies, Zoom, notes)
- Closed-won and closed-lost deals with any recorded reason
- CRM opportunity notes and stage history
- Deal desk / forecast call notes
- Any post-mortem write-ups

If you have a `.agents/product-marketing-context.md` file from the Product
Marketing pack, read it first for ICP, competitors, and positioning so findings
are framed against your actual market.

## Process

1. Confirm the evidence set and the time window (e.g. last two quarters). Note
   how many deals and transcripts are included - the report will state this.
2. Read every source. For each deal, capture: outcome (won/lost/no-decision),
   the reason it was recorded as won or lost on, and the moments in the
   transcript that reveal what actually moved the deal.
3. Cluster reasons across all deals. Merge duplicates that use different words
   for the same thing.
4. For each reason, separate what buyers said from what the pattern shows, and
   count how many deals it appears in.
5. Flag competitor-driven losses and group them by competitor.
6. Produce the report.

## Output format

A single document with:

- **Summary** - deals analyzed, time window, headline win reasons and loss
  reasons.
- **Loss reasons table** - reason | said or shown by pattern | number of deals |
  representative quote with source | so-what for PMM.
- **Win reasons table** - same columns.
- **Competitor breakdown** - for each competitor you lost to: pattern, the point
  in the deal it turned, and the counter that appears to work.
- **What this changes** - the two or three positioning, messaging, or enablement
  moves the evidence supports.

## The evidence standard

Every reason in the tables must cite at least one specific source - the deal
name, call date, or transcript line it came from. If a claim cannot be traced to
the material, it does not go in the report; it goes in a short "worth checking"
list at the end. Do not infer reasons the evidence does not support, and do not
smooth a messy finding into a clean one.
