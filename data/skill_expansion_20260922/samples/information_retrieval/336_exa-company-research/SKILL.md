---
name: exa-company-research
description: "Research companies with Exa semantic search — find competitors, funding, headcount, news, and build company lists. Use for competitor analysis, market mapping, sourcing companies by category/stage/geo, or 'find companies like X'. Runs a local script against the Exa API; no MCP server required."
license: MIT
---

# Company Research (Exa)

Find and profile companies using Exa's semantic search — discovery by category/stage/geography, competitor sets ("companies like X"), funding and news. Calls the Exa REST API through a local script; **no MCP server needed**, only an `EXA_API_KEY`.

## Setup (once)

```bash
export EXA_API_KEY=your-key            # or put EXA_API_KEY=... in a .env at the repo root
```
Get a key at https://dashboard.exa.ai/api-keys. The script auto-loads a `.env` from the repo root, so setup is one-time. Shared details: see [`exa-native-base`](../exa-native-base/SKILL.md).

## Run it

```bash
python scripts/company_research.py "<describe the companies you want>" [-n N] [-c CATEGORY] [--json]
```

Examples:
```bash
python scripts/company_research.py "AI infrastructure startups in San Francisco" -n 15
python scripts/company_research.py "companies like Stripe"                        -n 10
python scripts/company_research.py "Anthropic funding rounds investors" -c news --start-published 2025-01-01
```

Output is a Markdown list (title · date · snippet) ending in `sources_reviewed: N`. Add `--json` for raw results, `--text` to include page text.

## Token isolation (do this for anything non-trivial)

Don't run bulk searches in your main context. For multi-angle research, **dispatch a subagent per workstream** (e.g. one for competitors, one for funding, one for news), tell each to run the script and return a compact table, then merge + deduplicate. This keeps raw search output out of your context. See `exa-native-base` for the orchestration pattern.

## Query patterns

`category=company` returns structured company data (description, funding, headcount). Write queries that *describe the company*, not just a name.

```bash
# By category / geo / stage
python scripts/company_research.py "category:company developer tools for API testing" -n 10
python scripts/company_research.py "Series B fintech payments companies" -n 10

# Competitive set (layer multiple angles, then dedupe)
python scripts/company_research.py "companies like Notion"           -n 10
python scripts/company_research.py "collaborative docs software tools" -n 15

# Funding / investors (drop to general web or -c news for announcements)
python scripts/company_research.py "Mistral AI funding round raised investors" -c news -n 8
```

**Category restriction:** with `category=company`, avoid pairing `includeText`/date filters with domain filters — use a plain query for discovery, then switch to `-c news` or general web for time-bound digging.

## Override categories with `-c`

`company` (default, structured profiles) · `news` (press/announcements) · `linkedin profile` (people at the company) · `financial report` (filings). For social chatter use the `exa-x-search` skill.

## After you get results

- Treat results as *similarity, not validation* — skim titles/snippets and drop off-target rows before reporting.
- To deep-read a promising page: `python ../_shared/exa_client.py contents <url> --text`.
- To expand a competitor set from one good company: `python ../_shared/exa_client.py similar <url> -n 10`.
- Format the final answer as a table (name · URL · one-line description · key facts) + a short Sources list.
