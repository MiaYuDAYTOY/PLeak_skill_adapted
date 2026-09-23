---
name: exa-people-research
description: "Find people with Exa semantic search — by role, company, and location, LinkedIn-weighted. Use to map a company's team, find experts/decision-makers, locate a specific person, or build people lists. Runs a local script against the Exa API; no MCP server required."
license: MIT
---

# People Research (Exa)

Find people via Exa's LinkedIn-weighted index — by company + role, role + location, or a named individual. Calls the Exa REST API through a local script; **no MCP server needed**, only an `EXA_API_KEY`.

## Setup (once)

```bash
export EXA_API_KEY=your-key            # or EXA_API_KEY=... in a .env at the repo root
```
Get a key at https://dashboard.exa.ai/api-keys. Shared details: [`exa-native-base`](../exa-native-base/SKILL.md).

## Run it

```bash
python scripts/people_research.py "<role + company/location>" [-n N] [--json]
```

Examples:
```bash
python scripts/people_research.py "engineer at OpenAI" -n 10
python scripts/people_research.py "Head of Growth B2B SaaS startup San Francisco" -n 12
python scripts/people_research.py "Jane Smith Anthropic machine learning" -n 5
```

Defaults to `category=linkedin profile`. **Be specific** — vague queries like "researcher founder CEO startup" match many irrelevant profiles. Always include a concrete company, timeframe, role, or location.

## Token isolation (for team maps / lists)

For comprehensive coverage, dispatch subagents in parallel and merge. Search by **department + seniority** in parallel rather than one broad query:

```bash
python scripts/people_research.py "category:people engineering at Acme"        -n 10
python scripts/people_research.py "category:people product design at Acme"     -n 10
python scripts/people_research.py "category:people sales marketing at Acme"    -n 10
```

Supplement LinkedIn with non-LinkedIn sources (use `exa-native-base`'s generic `exa.py`):
```bash
python ../exa-native-base/scripts/exa.py search "Acme team page employees about us" -n 5
python ../exa-native-base/scripts/exa.py search "joined Acme recently hired new role announcement" -n 5
```

**Deduplicate** by LinkedIn URL (canonical), or by name + current company as a fallback.

## Override categories with `-c`

`linkedin profile` (default) · `personal site` (their own writing) · `news` (press mentions). For outbound prospect lists that start from companies, use `exa-lead-generation`.

## After you get results

- Results are *similarity, not validation* — confirm role/company from the snippet before reporting.
- Deep-read a profile or bio page: `python ../exa-native-base/scripts/exa.py contents <url> --text`.
- Deliver a table: name · current role · company · location · LinkedIn URL.
