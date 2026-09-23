---
name: zoom-summary
description: Read Zoom AI Companion meeting summaries through the Zoom REST API, save them as markdown, repair the domain terms Zoom mistranscribes, translate them to Korean, and hand decisions off to the research log. Use when the user asks about a past Zoom meeting, meeting summary, AI Companion notes, 회의록, 미팅 요약, 지난 미팅 내용, wants last week's Zoom meetings written up, or wants meeting-summary jargon or 용어 보정 fixed. Credentials live at `~/.config/zoom-skill/credentials.json`.
---

# Zoom Summary

Read-only access to Zoom AI Companion meeting summaries via the Zoom REST API v2, using a Server-to-Server OAuth app. Wraps the two summary endpoints with `curl` + `jq` helpers, and repairs the domain terms the summariser mistranscribes.

## Trigger conditions

Invoke this skill when the user says any of:
- "지난 미팅 요약 보여줘" / "what did we discuss in Monday's Zoom" / "last week's Zoom meetings" → `scripts/summaries.sh list`
- "그 미팅 요약 전체 내용" / "show me the full summary" → `scripts/summaries.sh get <uuid>`
- "요약 저장해줘" / "save that summary as markdown" → `scripts/summaries.sh save <uuid>`
- "용어 보정해줘" / "fix the mangled terms" / "그 약어 잘못 받아썼는데" → `scripts/correct.py`
- "set up Zoom" / "configure Zoom" / credentials file missing → follow the **Setup flow** below

## Prerequisites

Before any operation, check the credentials file exists:

    test -f ~/.config/zoom-skill/credentials.json

If it does not exist, run the setup flow below. Dependencies: `curl`, `jq`, `base64` (scripts exit 127 if missing), plus `python3` for `correct.py`.

The account must have AI Companion meeting summaries enabled, and the summaries must already have been generated and saved. This skill cannot generate a summary for a meeting that never had AI Companion on.

## Setup flow (skill-orchestrated)

The Zoom Marketplace app must be created by the user in a browser. You cannot do this step.

1. Check whether credentials already exist. If they do, ask before re-registering.
2. Give the user these steps verbatim:
   > 1. https://marketplace.zoom.us → Develop → Build App → **Server-to-Server OAuth**
   > 2. Scopes tab, add `meeting:read:list_summaries:admin` and `meeting:read:summary:admin`.
   >    If the picker does not offer them, add the classic scope `meeting_summary:read:admin`, which covers both.
   > 3. Activate the app.
   > 4. Copy **Account ID**, **Client ID**, **Client Secret** from App Credentials.
   >
   > These get stored at `~/.config/zoom-skill/credentials.json` (mode 600). Only paste them here if you trust this terminal and session transcript.
3. When the user replies with the three values, run the `--stdin` mode so the secret stays out of argv:
   ```bash
   bash scripts/setup.sh --stdin <<< '{"account_id":"<A>","client_id":"<I>","client_secret":"<S>"}'
   ```
4. Show the script's scope report verbatim. It prints `GRANTED` or `MISSING` per scope plus a live probe of the list endpoint.
5. On failure, show stderr verbatim and ask whether to retry.

**Do not** echo the client secret back in your own messages. **Do not** run setup unprompted; the triggers are an explicit request or a script exiting 2.

## Known scope gotcha

`meeting:read:summary:admin` (the summary *body* scope) is reported missing from the scope picker on some accounts. The symptom is that `list` works but `get` returns HTTP 403. If that happens:

1. Tell the user which scope the API refused, quoting the error.
2. Have them check for the classic `meeting_summary:read:admin` scope instead.
3. If neither is grantable, the zoom.us web portal (**Meeting Summary with AI Companion → My Summaries**) is the only remaining route. Say so plainly rather than retrying.

Do not auto-retry exit code 3.

## Script usage

All scripts live in this skill directory's `scripts/` folder.

### setup.sh — one-time credential registration

    bash scripts/setup.sh                  # interactive (TTY required)
    bash scripts/setup.sh --stdin <<< '<json>'

Verifies by minting a real token, writes credentials mode 600, then reports granted scopes and probes the list endpoint. There is no flag mode: a client secret on argv is visible in `/proc`.

### summaries.sh — the actual work

    bash scripts/summaries.sh list [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--json]
    bash scripts/summaries.sh get  <meetingUUID> [--json]
    bash scripts/summaries.sh save <meetingUUID> [--dir <path>] [--force]

- `list` defaults to the last 30 days and follows `next_page_token` to the end. Output is TSV: `start_time`, `topic`, `meeting_id`, `uuid`. Use the **uuid** column for `get` and `save`, not the meeting ID.
- `get` renders markdown by default; `--json` gives the raw body.
- `save` writes to `$ZOOM_SUMMARY_DIR` (default `~/Documents/ZoomSummaries`) as `YYYY-MM-DD_<topic-slug>.md` and prints the path. It refuses to overwrite without `--force`.

Meeting UUIDs often contain `/`, `+`, and `=`. Always quote them in shell commands. `auth.sh` handles Zoom's rule that a UUID starting with `/` or containing `//` must be double URL encoded; every other UUID goes through as is.

### correct.py — repair mangled domain terms

    python3 scripts/correct.py <file.md|-> [--in-place] [--report-only] [--no-appendix] [--glossary PATH]

Zoom's summariser mishears domain jargon consistently: acronyms come back as similar-sounding words, journal names get truncated, personal names get reversed. This applies the glossary and appends an audit table.

Two tiers, and the distinction is the whole point:

- `high` — substituted automatically.
- `low` — **never substituted**, only listed under "검토 필요" for a human to resolve. Terms whose correct form is unknown live here with `?` as the replacement.

`--in-place` keeps the untouched summary as `<stem>.raw.md`. Re-running re-derives from that raw file, so the run is idempotent, the substitution record survives, and glossary edits always apply to pristine text.

`--report-only` prints the report to stderr and writes nothing. `--no-appendix` corrects the text without appending the audit table. Reading from `-` (stdin) writes to stdout and cannot be combined with `--in-place`.

Glossaries load in order, later overriding earlier by pattern:

1. `references/glossary.tsv` in this skill — **template only**, ships with no real terms
2. `~/.config/zoom-skill/glossary.tsv` — where every real entry belongs (override the path with `ZOOM_SKILL_GLOSSARY`)
3. anything passed with `--glossary` (repeatable)

Requires `python3`. Exits 1 when the file is missing or no glossary entry exists anywhere, and 64 when `--in-place` is given with stdin.

## After fetching

1. **Term correction.** Run `correct.py --in-place` on every saved summary, then work the "검토 필요" list.

   Resolve unknowns against the research log before asking the user. For a project registered in `~/.research/`, `projects/<slug>/compass.md` carries the canonical vocabulary and paper structure, and `journal.md` carries verbatim usage. A term earns the `high` tier when you can cite the line that settles it: a garbled acronym in a sentence about a specific paper section resolves once compass.md says what that paper is about. Put the citation in the note column.

   Two limits worth knowing before you start digging. The research log holds **no personal names** at all, so mangled names never resolve there and must go to the user. And the log lags the meeting: it is a decision record, not a transcript, so a term coined in the meeting itself will not be in it.

   Everything you cannot cite stays `low`. Propose it to the user with your evidence and let them confirm; do not promote on plausibility alone. **All real entries go in `~/.config/zoom-skill/glossary.tsv`.** The skill's `references/glossary.tsv` is a template only: it is version controlled and may be pushed to a public remote, so project vocabulary and personal names must never be written there.
2. **Korean translation.** Produce `<basename>_ko.md` in the same directory. Skip it when the summary is already Korean, which it usually is when the meeting was. Per the user's global convention, delegate the translation to a Sonnet subagent, preserving the heading structure and any English proper nouns inside Korean sentences.
3. **research-log handoff.** When the user asks to log the meeting, use the `research-log` skill's record workflow. Pass only the decisions and action items, not the full summary text; a journal entry is not a transcript dump.
4. **Reporting.** Never paraphrase a summary as if it were the API's own words when you have not fetched it. If `list` returned rows but `get` failed, say which step failed. When you relay meeting content to the user, say plainly that AI Companion garbles proper nouns and that only glossary-backed terms have been repaired.

## Error handling

Show script stderr to the user verbatim. Exit code reference:

- 0 — success
- 1 — bad argument, `save` refused to overwrite, or `correct.py` found no file / no glossary entry
- 2 — credentials.json missing (→ run setup.sh)
- 3 — token rejected or scope missing, HTTP 401/403 (→ see the scope gotcha above)
- 4 — meeting UUID not found, HTTP 404 (often a UUID that needed quoting)
- 5 — other API error
- 6 — rate limited, HTTP 429
- 64 — usage error
- 127 — missing dependency

## Environment overrides

- `ZOOM_SKILL_CREDS` — credentials path (default `~/.config/zoom-skill/credentials.json`)
- `ZOOM_SKILL_CACHE` — token cache directory (default `~/.cache/zoom-skill`)
- `ZOOM_SUMMARY_DIR` — markdown output directory (default `~/Documents/ZoomSummaries`)
- `ZOOM_SKILL_GLOSSARY` — user glossary path (default `~/.config/zoom-skill/glossary.tsv`)
- `ZOOM_API_BASE`, `ZOOM_OAUTH_URL` — API and token endpoints. Only for pointing the scripts at a stand-in server during testing; never change them in normal use.

## API notes

Base `https://api.zoom.us/v2`. Tokens come from `POST https://zoom.us/oauth/token` with `grant_type=account_credentials`, live one hour, and are cached in `~/.cache/zoom-skill/token.json` keyed by a fingerprint of the credentials.

| Purpose | Endpoint |
|---|---|
| List summaries | `GET /meetings/meeting_summaries?from&to&page_size&next_page_token` |
| Summary body | `GET /meetings/{meetingUUID}/meeting_summary` |

Body fields: `summary_title`, `summary_overview`, `summary_details[].{label,summary}`, `next_steps[]`, `summary_start_time`, `summary_end_time`, `summary_created_time`, `meeting_host_email`.

Upstream docs: https://developers.zoom.us/docs/api/meetings/
