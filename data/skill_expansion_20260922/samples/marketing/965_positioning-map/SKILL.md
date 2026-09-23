---
name: positioning-map
description: >
  Read all of your competitors' public messaging alongside your own in one pass
  and map how each player frames itself - the category they claim, who they
  target, the value they lead with, and their proof. Shows where everyone is
  crowding onto the same claims and which angles are sitting unclaimed. Use when
  planning positioning or a launch, when a competitor makes a move, or when you
  need to see the whole competitive field at once rather than one rival at a
  time. Triggers: "map the competitive landscape," "how do competitors position,"
  "where can we differentiate," "everyone sounds the same," "competitive
  positioning."
---

# Positioning Map

## What this does

Reads the public positioning of your competitors and your own, and lays the whole
field out side by side. For each player it captures the category they claim, the
audience they target, the value they lead with, and the proof they lean on. Then
it shows two things: where the field is crowded (claims many players are making,
where you will not stand out) and which credible angles no one is currently
making.

Looking at one competitor at a time hides the pattern. Seeing them together is
what tells you where the room is.

## Why this is a Fable-recommended job

An honest read of the field means holding many competitors' full messaging in
view at once and comparing across all of it. Claude Fable 5 can take the whole
set - every rival's homepage, product pages, and category language plus your own
- in a single run and compare across it, which is what surfaces both the crowding
and the openings.

**If Fable is not available or the budget is spent:** capture each competitor's
positioning into a short standard profile one at a time, then load the profiles
together for the comparison pass. The profiles are smaller than the raw pages, so
the final comparison fits a smaller model.

## Evidence to gather first

- Each competitor's homepage, product pages, and category or "why us" pages
- Their pricing pages, if public
- Their recent launch or announcement copy
- Analyst or review-site category language (G2, Gartner summaries)
- Your own equivalent pages

Read `.agents/product-marketing-context.md` first if it exists, for your current
positioning and the competitor set that matters.

## Process

1. Confirm the competitor set and that you want your own positioning included
   (you usually do - it shows where you overlap with the field).
2. For each player, build a positioning profile: claimed category, target
   audience, primary value, top three claims, proof used, and tone.
3. Lay the profiles side by side. Identify the claims and angles multiple players
   share (the crowded ground).
4. Identify credible angles no player is making, and note for each whether you
   could actually support it with your product and evidence - an unclaimed angle
   you cannot back is not an opportunity.
5. Produce the map.

## Output format

- **Summary** - players analyzed, the crowded claims, the most promising
  unclaimed angles.
- **Positioning profiles** - one compact profile per competitor and for you.
- **Crowded ground** - the claims and angles multiple players share, with who is
  making each.
- **Unclaimed angles** - credible positions no one is taking, each with a note on
  whether your product and proof can support it.
- **So-what for us** - where you currently sit, and the two or three directions
  the map suggests are worth testing.

## The evidence standard

Every profile and every claim about a competitor must cite the page or source it
came from, and quote their actual language where it matters. Do not characterize
a competitor's positioning from memory or assumption - only from what is on their
pages. Mark an unclaimed angle as an opportunity only after checking whether you
can support it; otherwise label it "open but unsupported."
