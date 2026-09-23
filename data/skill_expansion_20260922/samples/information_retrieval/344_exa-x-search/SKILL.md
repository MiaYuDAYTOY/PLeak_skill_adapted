---
name: exa-x-search
description: "Search X/Twitter posts with Exa, filtered to x.com/twitter.com. Use for finding tweets or threads on a topic. NOTE: Exa's X coverage is limited (the tweet category was retired and X blocks crawlers), so results are often sparse — the skill is honest about this and suggests fallbacks. Runs a local script against the Exa API; no MCP server required."
license: MIT
---

# X / Twitter Search (Exa)

Search posts on x.com / twitter.com via Exa. Calls the Exa REST API through a local script; **no MCP server needed**, only an `EXA_API_KEY`.

## ⚠️ Read this first — coverage is limited

Exa **retired the `tweet` category**, and X blocks most crawlers, so X/Twitter content is sparsely indexed. This skill:
- filters results to x.com/twitter.com **client-side** (`--only-domains`), so you never get off-domain noise dressed up as tweets;
- **often returns few or zero results** — that's expected, not a bug;
- prints a clear note and fallback suggestions when empty.

For reliable social/sentiment coverage, treat this as best-effort and use the fallbacks below.

## Setup (once)

```bash
export EXA_API_KEY=your-key            # or EXA_API_KEY=... in a .env at the repo root
```
Get a key at https://dashboard.exa.ai/api-keys. Shared details: [`exa-native-base`](../exa-native-base/SKILL.md).

## Run it

```bash
python scripts/x_search.py "<topic / handle / thread>" [-n N] [--json]
```

Examples:
```bash
python scripts/x_search.py "Anthropic Claude launch reactions" -n 15
python scripts/x_search.py "founder thread lessons scaling startup" -n 15
```

The script forces `--include-domains x.com,twitter.com` and `--only-domains x.com,twitter.com`. If it returns `sources_reviewed: 0`, that's the coverage limit, not an error.

## Fallbacks when X coverage is thin

1. **Find discussion *about* the topic on the open web** (Reddit, HN, blogs, news):
   ```bash
   python ../exa-company-research/scripts/company_research.py "<topic> reaction analysis commentary" -c news -n 15
   python ../exa-native-base/scripts/exa.py search "<topic> discussion hacker news reddit" -n 15
   ```
2. **Read a known thread/profile directly** (if you have the URL):
   ```bash
   python ../exa-native-base/scripts/exa.py contents https://x.com/<user>/status/<id> --text
   ```
3. **Use a dedicated X/Twitter API** for real-time, exhaustive social data — Exa is not the right tool for that.

## After you get results

- Verify each result is actually a relevant x.com/twitter.com post (the domain filter guarantees the host, not the relevance).
- Be explicit in your answer about coverage: state how many on-platform posts you found and whether you fell back to the open web.
- Deliver: author/handle · post link · one-line gist; note the recency.
