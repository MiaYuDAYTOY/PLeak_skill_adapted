---
name: exa-code-context
description: "Find code with Exa — API usage examples, error fixes, library docs, and GitHub repositories. Use when you need a working code snippet, to resolve an error, find an open-source implementation, or pull up official docs for a language/framework. Runs a local script against the Exa API; no MCP server required."
license: MIT
---

# Code Context (Exa)

Find code examples, API usage, documentation, error fixes, and GitHub repos via Exa. Calls the Exa REST API through a local script; **no MCP server needed**, only an `EXA_API_KEY`.

## Setup (once)

```bash
export EXA_API_KEY=your-key            # or EXA_API_KEY=... in a .env at the repo root
```
Get a key at https://dashboard.exa.ai/api-keys. Shared details: [`exa-native-base`](../exa-native-base/SKILL.md).

## Run it

```bash
python scripts/code_context.py "<query — always include language + library>" [-n N] [-c github] [--text]
```

Examples:
```bash
python scripts/code_context.py "Stripe API create subscription Node.js code example" -n 8
python scripts/code_context.py "React hydration mismatch server client explanation fix" -n 10
python scripts/code_context.py "production-ready vector database in Rust" -c github -n 10
```

**Always include the programming language and framework/library** in the query — it sharply improves relevance. No default category (most code/docs/error pages live on the open web); add `-c github` to discover repositories.

## Query patterns

```bash
# API usage
python scripts/code_context.py "Stripe API create subscription Node.js code example" -n 5

# Error resolution (describe the error + stack)
python scripts/code_context.py "Next.js 'window is not defined' SSR error fix" -n 10

# GitHub implementations / repos
python scripts/code_context.py "open-source example project using LangGraph" -c github -n 10
```

## Reading docs you already know

When you have the doc/repo URL, skip search and read it directly:
```bash
python ../exa-native-base/scripts/exa.py contents https://fastapi.tiangolo.com/tutorial/background-tasks/ --text
```

## Override categories with `-c`

(no default) general web — best for docs, tutorials, Stack Overflow, error fixes · `github` — repositories · `pdf` — spec/RFC PDFs.

## After you get results

- Prefer official docs and well-starred repos; treat results as *similarity, not validation* — open the page and confirm the snippet actually solves the problem before relying on it.
- For a multi-part investigation (e.g. "how do teams do X across libraries"), dispatch subagents per library and compare approaches.
- Deliver: the working snippet/answer first, then the source links it came from.
