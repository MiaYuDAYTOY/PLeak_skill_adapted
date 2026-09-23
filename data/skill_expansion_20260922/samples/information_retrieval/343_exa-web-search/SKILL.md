---
name: exa-web-search
description: "General-purpose web search powered by Exa — the search_web / web_search analog. Use for any open-ended lookup, fact-finding, or 'search the web for X' when no specialized skill fits. Semantic (meaning-based) search over the whole index; runs a local script against the Exa API, no MCP server required."
license: MIT
---

# Web Search (Exa)

Plain semantic web search — the everyday `search_web` you reach for first. No category, no domain restriction: describe what you're looking for and Exa returns the closest pages. Calls the Exa REST API through a local script; **no MCP server needed**, only an `EXA_API_KEY`.

**This skill is self-contained** — its client (`scripts/exa_client.py`) is vendored, so you can install just this folder.

## Install

Get a key first at https://dashboard.exa.ai/api-keys, then:

```bash
export EXA_API_KEY=your-key          # add to ~/.zshrc / ~/.bashrc to make it permanent
```

**Just this skill (Claude Code):**
```bash
git clone --depth 1 https://github.com/CodeAlive-AI/exa-skills /tmp/exa-skills
cp -r /tmp/exa-skills/exa-web-search ~/.claude/skills/exa-web-search   # user-level
#   …or  .claude/skills/exa-web-search  inside a project for project-level
```
That's the whole install — no other folders required. (Other agents: drop the `exa-web-search` folder wherever your agent discovers skills.)

**Whole collection:** clone the repo and point your agent at it — see the [repo README](https://github.com/CodeAlive-AI/exa-skills).

## Run it

```bash
python scripts/web_search.py "<what you're looking for>" [-n N] [--text] [--json]
```

Examples:
```bash
python scripts/web_search.py "how do vector databases handle deletes" -n 10
python scripts/web_search.py "best practices for prompt caching with LLMs" --text
python scripts/web_search.py "self-hosted analytics alternatives to Google Analytics" -n 12
```

Output is a Markdown list (title · date · snippet) ending in `sources_reviewed: N`. `--text` includes page content, `--json` gives raw results, `-h` lists all flags.

## Write queries that describe the page

Exa is semantic, not keyword. **Describe the page you want to find, not the keywords.** "detailed blog post about X written by a practitioner" beats "X". Run 2-3 different *angles* (not synonyms) in parallel for coverage.

Handy flags when you need them:
- `-c company|news|research paper|github|pdf|personal site|linkedin profile|financial report` — focus a category without leaving this skill.
- `--include-domains a.com,b.com` / `--start-published 2025-01-01` — scope by site or date.
- `--text` — pull page content when snippets aren't enough.

## More than search (same vendored client)

```bash
python scripts/exa_client.py contents <url> --text      # read a page's full content
python scripts/exa_client.py answer "<question>"        # a direct, cited answer
python scripts/exa_client.py similar <url> -n 10        # pages similar to a URL
```

## Token isolation (for multi-search tasks)

For anything beyond 1-2 queries, dispatch a subagent per angle (use the Agent tool), have each run this script and return a compact list, then merge + deduplicate. Keeps raw search output out of your main context.

## After you get results

- Treat results as *similarity, not validation* — skim and drop off-target hits before relying on them.
- Lead your answer with the finding; cite source URLs inline; prefer a table when fields are uniform.

---
*Part of the [Exa Skills](https://github.com/CodeAlive-AI/exa-skills) collection. For specialized research (companies, people, papers, code, finance, personal sites, X) install the matching skill from the repo.*
