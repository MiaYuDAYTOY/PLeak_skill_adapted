---
name: office-skills
description: Use this skill when you need to create, edit, convert, analyze, validate, or QA Office/document artifacts: DOCX, XLSX, PPTX, PDF, HTML dashboards, business reports, Vietnamese administrative documents, or raw data to chart/report workflows. It routes the task, asks for missing source/template/field/business-rule/output details, uses the bundled resources/scripts, and verifies that the final artifact opens correctly and is not blank or repair-required.
---

# office-skills

Office automation skill for agents that need to handle documents and workplace data safely and reproducibly.

This skill is intentionally a router plus toolkit. The user should not need to know whether the right workflow is DOCX, XLSX, PPTX, PDF, Office XML, dashboard, report, or conversion. Determine the shortest workflow that produces a correct verified output.

## Use this skill when

- Creating or editing `.docx`, `.xlsx`, `.pptx`, `.pdf`, `.html` dashboards, charts, or reports.
- Converting between document formats.
- Extracting tables/text from Office or PDF files.
- Filling a template while preserving layout and style.
- Turning raw data into cleaned tables, charts, dashboards, or narrative reports.
- Creating Vietnamese administrative documents or formal business documents.
- Validating Office files after generation or OOXML patching.

## Do not use this skill when

- The user only asks a general programming question unrelated to documents or workplace data.
- The user asks for destructive edits to original files without explicit confirmation.
- The task needs cloud-only integrations or credentialed systems that are not available locally.

## Core rules

1. Ask before acting if missing details can change the output: source files, template/format to preserve, sheet/table/page/slide, fields, business rules, filters, output format, or overwrite risk.
2. Never overwrite source files unless the user explicitly requests it.
3. Prefer local, simple, reproducible workflows.
4. For raw data to chart/dashboard/report, create checked bridge artifacts before rendering final output.
5. For template-based work, profile the template before patching or rendering.
6. Do not hard-code report year, source filename, sheet name, title/subtitle, or business filters when they can be inferred from data.
7. Do not report completion if an Office file needs repair, is blank, or lacks its main expected content.
8. Run headless/hidden Office automation when possible; do not bring Word/Excel/PowerPoint windows to the user's screen unless requested.
9. If a bundled script fails because of environment/path/version assumptions, only patch the bundled script when working inside this `office-skills` repo. When the skill is installed as a runtime package, copy or create a task-local script in the target project's `scripts/` and patch that local copy instead.

## Repository assets

Read the most relevant asset before producing professional output:

| Need | Read/use |
|---|---|
| DOCX creation/editing | `resources/docx.md`, `standards/structure/docx-*.md`, `standards/color/docx-*.md` |
| Vietnamese administrative DOCX | `standards/nd30.md`, `templates/docx-hanh-chinh-*.md` |
| XLSX report/dashboard | `resources/xlsx.md`, `standards/structure/xlsx-structure.md`, `standards/color/xlsx-palettes.md` |
| PPTX presentation | `resources/pptx.md`, `standards/structure/pptx-structure.md`, `standards/color/pptx-palettes.md` |
| PDF extraction/conversion | `resources/pdf.md`, `resources/convert.md` |
| Preserve Office template format | `resources/office-xml.md`, `scripts/office/unpack.py`, `scripts/office/pack.py`, `scripts/office/clone_text.py` |
| Library/tool selection | `resources/library-selection.md` |
| Bridge artifacts | `resources/bridge.md` |

Do not copy bundled resources into the target project unless the workflow needs a reusable script or local project memory.

## Workflow router

Classify the request first:

### A. Explain / inspect only

Answer directly or inspect the file. Do not bootstrap folders or create scripts unless needed.

### B. Simple one-step task

Examples: convert one file, extract one small table, inspect a workbook, create a simple document. Use the shortest safe workflow. If writing a file, create only `output/` unless the task needs reusable scripts, remembered requirements, template profiling, or error lessons.

### C. Multi-step workflow

Examples: multiple source files, cleaning/aggregation, charts, dashboards, reports, template filling, multi-format output. Bootstrap target project memory and bridge artifacts at the minimum level needed for traceability and reruns.

## Intake checklist

Before group B/C workflows, confirm only the missing items that affect correctness:

- Purpose: what final artifact and what audience/use?
- Source: which file(s), sheet/table/page/slide/range, header row, primary source vs lookup/template?
- Fields: period, entity, category, measure, status, ID, owner, mapping.
- Business rules: filters, exclusions, grouping, aggregation, ranking, top N, rounding, date/currency/percent formats.
- Template/format: whether layout, style, logo, fonts, formulas, charts, slide masters, or headers/footers must be preserved.
- Output: format, name, folder, language, tone, required KPIs/charts, validation criteria.

When file inspection can answer a question safely, inspect first and state assumptions rather than asking the user to enumerate everything.

## Target project bootstrap

Bootstrap only as much structure as the task needs:

| Task level | Create/use |
|---|---|
| Explain or inspect only | No project bootstrap. |
| Simple one-step output | `output/` only. |
| Simple task with reusable script or observed error | `output/`, `scripts/`, `LOG.md`. |
| Template-preserving task | `output/`, `INSTRUCT.md`, `LOG.md`; add `scripts/` if automation is saved. |
| Raw data to chart/dashboard/report | `output/`, `bridge/`, `INSTRUCT.md`, `LOG.md`; add `scripts/` when rerunnable automation is useful. |
| Long-lived Office automation workspace | Optional `CLAUDE.md` only when the user wants persistent project-level agent instructions. |

- `INSTRUCT.md`: confirmed requirements, source/template roles, field mapping, business rules, template profile, output requirements, validation checklist.
- `LOG.md`: execution issues, environment/script fixes, repair/blank-output causes, and things not to repeat.
- `bridge/`: cleaned data, summaries, chart sources, metadata, validation, evidence.
- `output/`: final user-facing artifacts only.
- `CLAUDE.md`: optional target-project agent context, not required for one-off tasks.

Read existing `INSTRUCT.md` and `LOG.md` before workflows that use or update them.

## Default workflows

| Situation | Workflow |
|---|---|
| Read/inspect file | EXTRACT |
| Merge tabular files | EXTRACT → MERGE |
| Clean/summarize data | EXTRACT/MERGE → TRANSFORM |
| Create polished Excel | TRANSFORM → CREATE_EXCEL |
| Create chart | TRANSFORM → CREATE_CHART |
| Create dashboard | TRANSFORM → CREATE_CHART → CREATE_DASHBOARD |
| Create report | TRANSFORM → CREATE_CHART → CREATE_REPORT |
| Create Word document | CREATE_DOCX |
| Create PowerPoint | CREATE_PPTX |
| Convert format | CONVERT |
| Preserve existing Office formatting | OFFICE_XML |

Choose the simpler valid workflow.

## Library and tool priority

Use `resources/library-selection.md` as the decision table. In short:

- Tables/data: `pandas` + `numpy`; read/write Excel with `openpyxl` or `xlsxwriter`; `.xlsb` with `pyxlsb`.
- XLSX editing with existing formulas/styles: `openpyxl`; new styled report workbooks: `xlsxwriter` or `openpyxl` depending on formula/edit needs.
- DOCX new documents: `python-docx`; Markdown to DOCX: bundled converter or Pandoc + `scripts/format/format_docx.py`; preserving template format: Office XML scripts.
- PPTX basic generation/editing: `python-pptx`; complex template-preserving changes: Office XML; visual QA: LibreOffice/PowerPoint headless export when available.
- PDF text/tables: `pdfplumber`; merge/split/page operations: `pypdf`; PDF to DOCX: `pdf2docx`; generated PDFs: `reportlab`; scanned PDFs: vision/OCR workflow, not digital extraction.
- OOXML safety/validation: bundled `scripts/office/*`, `defusedxml`, `lxml`, `zipfile` checks.
- Charts/dashboards: `plotly` for interactive/static HTML; `matplotlib` only if already available or needed; prefer HTML dashboards when no dynamic app is required.

## Bridge requirements for reports/dashboards

For raw data to chart/dashboard/report, do not render directly from raw source when traceability matters. Create bridge artifacts such as:

```text
bridge/01-cleaned-data.xlsx
bridge/02-summary-tables.xlsx
bridge/03-chart-sources.xlsx
bridge/metadata.json
bridge/validation.txt
bridge/evidence.json
bridge/qa.log
```

At minimum, metadata should record source file, sheet/page where relevant, report period, business filters, row counts, entity counts, field mapping, and output path.

## Template profile requirement

When a file is a format/template source and the user expects formatting preservation, profile before rendering:

- DOCX: page size, margins, sections, headers/footers, styles, fonts, heading/list/table styles, image/shape positions.
- XLSX: sheets, column widths, row heights, merged ranges, formats, formulas, freeze panes, filters, fills, borders, charts, images, print setup.
- PPTX: slide size, masters/layouts, shape tree, placeholders, geometry, fonts, fills, lines, images, charts, z-order.

If a library cannot profile an important part, record the limitation in `INSTRUCT.md` and use Office XML, COM, or LibreOffice where necessary.

## Verification checklist

Use the lightest verification tier that proves the requested outcome:

### Basic verification

Use for simple extraction/conversion/creation:
- Confirm the output file exists in `output/` or the requested path.
- Reopen/read it with the appropriate library: `python-docx`, `openpyxl`, `python-pptx`, `pypdf`, `zipfile`, or OOXML validation.
- Confirm expected document elements are non-zero: paragraphs/tables, sheets/cells, slides/shapes/images, pages/text/tables.

### Data/report verification

Use when output is based on source data, business rules, charts, dashboards, or reports:
- Perform Basic verification.
- Reconcile final KPI/chart/table values against bridge tables.
- Confirm metadata: source file, sheet/page where relevant, period, filters, row counts, field mapping, and output path.
- Check title/subtitle, period, filters, source name, chart readability, and label wrapping/truncation.

### High-fidelity visual verification

Use when template fidelity, presentation quality, copied images/charts, or final client-facing layout matters:
- Perform Basic and Data/report verification as applicable.
- For Office XML edits, pack correctly and run `scripts/office/validate.py` when applicable.
- Render/export DOCX/PPTX/PDF pages/slides to PDF/PNG when tools are available.
- Check fonts, text overflow, spacing, contrast, image/chart dimensions, z-order, and blank frames.

Do not escalate to heavier verification just because it is possible; use it when the task risk justifies it.

## Response format

For completed tasks, answer briefly with:

- What was done.
- Input files used.
- Output path(s).
- Bridge files created, if any.
- Scripts saved/changed, if any.
- Assumptions or remaining limits, if any.

If the task was only explanation or inspection, answer directly without forcing file creation.
