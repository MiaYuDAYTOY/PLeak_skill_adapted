---
name: exa-lead-generation
description: "Build prospect lists with Exa — find target companies matching an ICP, then their decision-makers, then enrich with signals. Use for outbound sales lists, account mapping, and B2B prospecting. Multi-pass orchestration over the Exa API; no MCP server required."
license: MIT
---

# Lead Generation (Exa)

Turn an ICP into a prospect list: **companies → decision-makers → enrichment**. This is a multi-pass workflow built on `exa-company-research` and `exa-people-research`. Calls the Exa REST API through local scripts; **no MCP server needed**, only an `EXA_API_KEY`.

## Setup (once)

```bash
export EXA_API_KEY=your-key            # or EXA_API_KEY=... in a .env at the repo root
```
Get a key at https://dashboard.exa.ai/api-keys. Shared details: [`exa-native-base`](../exa-native-base/SKILL.md).

## The pipeline

**Pass 1 — Source companies (this skill's script):**
```bash
python scripts/lead_generation.py "Series A B2B SaaS companies in fintech" -n 20
python scripts/lead_generation.py "category:company developer tools startups hiring backend 2026" -n 20
```
Run 2-3 angles (category, stage, recent-launch) and dedupe to a clean company list.

**Pass 2 — Find decision-makers at each company** (use `exa-people-research`, batch 3-5 companies per subagent):
```bash
python ../exa-people-research/scripts/people_research.py "VP Engineering at <Company>" -n 5
python ../exa-people-research/scripts/people_research.py "Head of Sales at <Company>" -n 5
```

**Pass 3 — Enrich** (funding, hiring, news signals → timing):
```bash
python ../exa-company-research/scripts/company_research.py "<Company> funding round hiring news" -c news -n 5
```

## Token isolation (essential here)

This is a fan-out task. **One subagent per batch of seeds** (3-5 companies each), each running Passes 2-3 and returning a compact table. Then compile, dedupe by company + person, and rank. Never run the whole enrichment loop in your main context. See `exa-native-base` for the orchestration pattern.

## Qualifying & enriching rows

- Define what makes a valid lead *before* searching (stage, geo, headcount, tech stack, buying signal).
- Capture a consistent schema per row: company · website · why-it-fits · contact name · role · profile URL · signal (hiring/funding/launch) · source.
- Apply **hard filters first** (stage, geo), then **soft filters** (genuine fit). See `references/filtering.md` in `exa-native-base`.

## Finding hidden connections

For "who are X's customers / partners", direct queries return articles, not connections. Use indirect signals:
```bash
python ../exa-company-research/scripts/company_research.py "<Company> case study customer success story" -n 5
python ../exa-native-base/scripts/exa.py contents https://company.com/customers https://company.com/case-studies --text
```

## After you get results

Deliver a deduped table (company · fit · contact · role · profile · signal · source), lead with the highest-signal accounts, and note coverage gaps. Treat results as *similarity, not validation* — verify before outreach.
