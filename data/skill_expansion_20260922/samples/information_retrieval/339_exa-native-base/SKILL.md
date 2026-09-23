---
name: exa-native-base
description: "Foundation for the Exa skill collection — how to call Exa (search, contents, answer, similar) from a local script with just an EXA_API_KEY, how to write good semantic queries, and how to orchestrate subagents for deep research. Read this first; the use-case skills (company, people, papers, code, news, finance, personal sites, X) build on it."
license: MIT
---

# Exa Native Base

The shared foundation for every Exa skill in this collection. Exa is a **semantic** search engine (vector embeddings, not keywords) plus content-fetch and answer APIs. These skills call the Exa REST API directly through a local Python script — **no MCP server, no SDK install**, only an API key.

## Setup (once)

```bash
export EXA_API_KEY=your-key            # or create a .env at the repo root: EXA_API_KEY=...
```
Get a key at https://dashboard.exa.ai/api-keys. The client (`_shared/exa_client.py`) auto-loads a `.env` found by walking up from the script, so any skill works from any directory once the key is set. Python 3.8+, standard library only.

## The client

One zero-dependency CLI backs all skills: `_shared/exa_client.py` (also exposed here as `scripts/exa.py`).

```bash
python scripts/exa.py search "<query>" [-n N] [-c CATEGORY] [-t TYPE] [--text] [--json] \
                                       [--include-domains a.com,b.com] [--only-domains a.com] \
                                       [--start-published 2025-01-01] [--include-text "phrase"]
python scripts/exa.py contents <url> [<url> ...] [--text] [--summary]
python scripts/exa.py answer  "<question>" [--text]
python scripts/exa.py similar <url> [-n N]
```

Every `search` prints a Markdown list and a trailing `sources_reviewed: N` line so an orchestrator can tally coverage.

## Writing good queries (read this)

**Describe the page you want to find, not the fact you want to know.** Exa returns nearest neighbours in embedding space; it does not do keyword matching, boolean logic, or quoted exact-match.

| Looking for | Weak query | Strong query |
|---|---|---|
| Blog posts about X | `X` | `detailed blog post about X written by a practitioner` |
| A company doing Y | `Y company` | `category:company startup building Y for enterprise` |
| A person | `person at company` | `category:people senior infra engineer at Acme` |

- **Categories** focus the index. Pass with `-c`: `company`, `research paper`, `news`, `pdf`, `github`, `personal site`, `linkedin profile`, `financial report`. You can also write `category:company …` inline in the query. *(The old `tweet` category was retired — `exa-x-search` handles X via domain filters.)*
- **`numResults` sizing:** named entity → ~5; precise filter → ~10; broad discovery → ~15. Never go above 25 — run more queries at different angles instead of one huge query.
- **Query diversity:** vary the *angle* (skeptic vs builder vs practitioner), not just synonyms. Word order shifts embeddings, so 2-3 phrasings in parallel widen coverage.
- **Dates:** compute exact dates from today's date *first*, then either encode them in the query ("published in March 2026") or use `--start-published` / `--end-published`. Never reuse dates from examples.
- **`type`:** `auto` (default) is fine for almost everything; `fast` for latency; `deep` / `deep-reasoning` for hard multi-hop questions.

## Token isolation & orchestration (for deep research)

Never dump bulk search output into your main context. When a task needs more than 1-2 searches:

1. **Plan** the sub-questions / workstreams (e.g. competitors, funding, hiring).
2. **Dispatch one subagent per workstream** (use the Agent tool; `model: haiku` is enough). Tell each: which skill script to run, which queries, what to return. Aim for 3-5 searches per subagent; launch them in parallel.
3. **Compile**: merge results, drop exact-URL duplicates, merge same-entity rows, note "deduplicated X → Y".
4. **Validate coverage** and fill gaps with targeted follow-ups.
5. **Deliver** a tight, well-formatted answer (prefer tables; hyperlink sources; lead with the answer).

Treat Exa results as *similarity, not validation* — always review and filter before reporting.

## Reference files (read on demand)

| File | When |
|---|---|
| `references/searching.md` | Full query-writing guide and category index |
| `references/filtering.md` | Apply hard + soft filters to results |
| `references/extraction.md` | Pull structured fields into a schema |
| `references/synthesis.md` | Write a narrative answer with citations |
| `references/source-quality.md` | Judge source credibility (best-of / expert queries) |
| `references/python-sdk-spec.md` | Full Exa API surface (search/contents/answer/research, all params) |

## The collection

| Skill | Use for |
|---|---|
| `exa-web-search` | General web search — the `search_web` analog; start here for open-ended lookups |
| `exa-company-research` | Companies, competitors, funding, market maps |
| `exa-people-research` | People by role/company/location (LinkedIn-weighted) |
| `exa-lead-generation` | Prospect lists: companies → decision-makers |
| `exa-research-paper-search` | Academic papers, surveys, preprints |
| `exa-code-context` | Code, APIs, docs, GitHub repos, error fixes |
| `exa-financial-report-search` | SEC filings, earnings, annual reports |
| `exa-personal-site-search` | Personal blogs, portfolios, homepages |
| `exa-x-search` | X/Twitter posts (limited — see that skill's notes) |

---
*Query patterns and research guidance adapted from Exa Labs' open-source search skill (MIT). This collection reimplements them as standalone, script-based skills that need no MCP server.*
