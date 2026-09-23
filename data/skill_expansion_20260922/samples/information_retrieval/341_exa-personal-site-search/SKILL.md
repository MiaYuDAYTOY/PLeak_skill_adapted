---
name: exa-personal-site-search
description: "Find personal websites with Exa — blogs, portfolios, and homepages. Use to find a person's own writing (not press about them), discover practitioners who blog, or surface indie/portfolio sites. Runs a local script against the Exa API; no MCP server required."
license: MIT
---

# Personal Site Search (Exa)

Find personal blogs, portfolios, and homepages via Exa's personal-site index — a person's *own* voice rather than coverage of them. Calls the Exa REST API through a local script; **no MCP server needed**, only an `EXA_API_KEY`.

## Setup (once)

```bash
export EXA_API_KEY=your-key            # or EXA_API_KEY=... in a .env at the repo root
```
Get a key at https://dashboard.exa.ai/api-keys. Shared details: [`exa-native-base`](../exa-native-base/SKILL.md).

## Run it

```bash
python scripts/personal_site_search.py "<who / what they write about>" [-n N] [--text]
```

Examples:
```bash
python scripts/personal_site_search.py "machine learning engineer personal blog" -n 10
python scripts/personal_site_search.py "indie hacker building in public portfolio" -n 12
python scripts/personal_site_search.py "Andrej Karpathy personal site essays" -n 5
```

Defaults to `category=personal site`.

## Query patterns

```bash
# Practitioners who write about a topic
python scripts/personal_site_search.py "category:personal site distributed systems engineer blog" -n 12

# A specific person's own site
python scripts/personal_site_search.py "category:personal site <name> blog essays projects" -n 5

# Portfolios in a discipline
python scripts/personal_site_search.py "category:personal site product designer portfolio case studies" -n 12
```

## Hidden relationships & terminology

Personal sites are ideal for finding non-obvious connections (collaborators, longtime clients, mentors) that aren't listed anywhere. Use indirect signals:
```bash
python scripts/personal_site_search.py "<subject> conversation interview testimonial guest" -n 8
python ../exa-native-base/scripts/exa.py search "<subject> years decades longtime worked with known since" -n 10
```
Detect insider terminology on the subject's own pages, then search for others using those terms. (See the relationships pattern in `exa-lead-generation`.)

## Override categories with `-c`

`personal site` (default) · `linkedin profile` (their professional profile) · `news` (press about them).

## After you get results

- This index favours genuine personal sites; still treat results as *similarity, not validation* and open the page to confirm it's the right person.
- Deep-read with `python ../exa-native-base/scripts/exa.py contents <url> --text` to assess voice/expertise.
- Deliver: name · site URL · what they write about · a representative post.
