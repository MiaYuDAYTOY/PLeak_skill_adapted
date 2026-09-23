---
name: exa-financial-report-search
description: "Find financial filings with Exa — SEC filings (10-K, 10-Q, S-1), earnings reports, and annual reports. Use to pull a company's financials, compare results across periods, or locate a specific filing. Runs a local script against the Exa API; no MCP server required."
license: MIT
---

# Financial Report Search (Exa)

Find SEC filings, earnings, and annual reports via Exa's financial-report index. Calls the Exa REST API through a local script; **no MCP server needed**, only an `EXA_API_KEY`.

## Setup (once)

```bash
export EXA_API_KEY=your-key            # or EXA_API_KEY=... in a .env at the repo root
```
Get a key at https://dashboard.exa.ai/api-keys. Shared details: [`exa-native-base`](../exa-native-base/SKILL.md).

## Run it

```bash
python scripts/financial_report_search.py "<company + report type + fiscal year>" [-n N] [--text]
```

Examples:
```bash
python scripts/financial_report_search.py "Nvidia 10-K annual report fiscal 2024 revenue" -n 8
python scripts/financial_report_search.py "Tesla Q3 2025 earnings results guidance" -n 8
python scripts/financial_report_search.py "Stripe S-1 filing prospectus" -c pdf -n 5
```

Defaults to `category=financial report`. **Encode the report type and fiscal year** (10-K, 10-Q, S-1, 8-K, earnings; FY/quarter) — it's the strongest relevance signal.

## Query patterns

```bash
# Annual / quarterly filings
python scripts/financial_report_search.py "Apple 10-K fiscal 2023 risk factors segment revenue" -n 8

# Earnings & guidance
python scripts/financial_report_search.py "Microsoft Q2 FY2025 earnings call revenue cloud guidance" -n 8

# Primary source on SEC EDGAR
python ../exa-native-base/scripts/exa.py search "Nvidia 10-K 2024" --include-domains sec.gov -n 8
```

## Reading the actual numbers

Search finds the filing; **read it** to extract figures:
```bash
python ../exa-native-base/scripts/exa.py contents <filing-url> --text
```
For long filings, fetch the specific document (not the index) and pull the line items you need. Distinguish reported figures from estimates, and always cite the filing URL + period.

## Override categories with `-c`

`financial report` (default) · `pdf` (PDF filings/prospectuses) · `news` (analyst/press coverage) · `company` (company profile/context).

## After you get results

- Prefer **primary sources** (sec.gov / investor-relations) over secondary commentary for figures.
- Treat results as *similarity, not validation* — confirm the company, period, and figure from the filing itself.
- Deliver: the figures with their period and a link to the exact filing; flag any number you couldn't verify in a primary source.
