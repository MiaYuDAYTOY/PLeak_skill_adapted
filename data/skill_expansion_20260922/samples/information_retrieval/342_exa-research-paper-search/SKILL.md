---
name: exa-research-paper-search
description: "Find academic papers with Exa — by topic, author, recency, or as surveys/reviews. Use for literature reviews, finding seminal or state-of-the-art papers, tracking recent preprints (arXiv), or building a reading list. Runs a local script against the Exa API; no MCP server required."
license: MIT
---

# Research Paper Search (Exa)

Find academic papers and preprints via Exa's research-paper index (arXiv and beyond). Calls the Exa REST API through a local script; **no MCP server needed**, only an `EXA_API_KEY`.

## Setup (once)

```bash
export EXA_API_KEY=your-key            # or EXA_API_KEY=... in a .env at the repo root
```
Get a key at https://dashboard.exa.ai/api-keys. Shared details: [`exa-native-base`](../exa-native-base/SKILL.md).

## Run it

```bash
python scripts/research_paper_search.py "<topic / method>" [-n N] [--json]
```

Examples:
```bash
python scripts/research_paper_search.py "sparse attention mechanisms for long context transformers" -n 12
python scripts/research_paper_search.py "diffusion models comprehensive survey review" -n 10
python scripts/research_paper_search.py "Geoffrey Hinton forward-forward algorithm" -n 5
```

Defaults to `category=research paper`.

## Query patterns

```bash
# By topic
python scripts/research_paper_search.py "category:research paper retrieval augmented generation robustness" -n 12

# Survey / review papers (best entry point into a field)
python scripts/research_paper_search.py "category:research paper <topic> comprehensive survey review" -n 10

# By author
python scripts/research_paper_search.py "category:research paper <author name> <topic>" -n 5

# By recency — encode the year(s) in the query (don't rely on date filters alone)
python scripts/research_paper_search.py "category:research paper large language model agents 2025 2026" -n 15
```

**To find seminal papers:** search for survey/review papers first, then deep-read them to extract the foundational references they cite.

## Token isolation (for a literature review)

Decompose into sub-topics and dispatch a subagent per branch (e.g. architectures, training, evaluation, limitations). Each runs 3-5 paper searches and returns a compact table (title · authors · year · venue/arXiv id · one-line contribution). Merge, dedupe by title/arXiv id, then synthesize.

## Override categories with `-c`

`research paper` (default) · `pdf` (when the paper is a standalone PDF) · `news` (coverage of a result). For code accompanying a paper, use `exa-code-context`.

## After you get results

- Deep-read abstracts/sections: `python ../exa-native-base/scripts/exa.py contents <arxiv-url> --text`.
- For a narrative review, see `references/synthesis.md` in `exa-native-base` — organize by theme, cite every claim, surface disagreements.
- Deliver a table (title · authors · year · link · contribution) or a themed synthesis with citations.
