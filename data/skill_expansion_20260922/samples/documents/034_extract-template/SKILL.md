---
name: extract-template
description: Extract a clean PPTX template (masters, layouts, theme) from an existing presentation and generate a markdown skeleton documenting available layouts. Use when the user wants to extract a template from a pptx file, create a reusable template, or inspect available slide layouts.
license: MIT
compatibility: Requires python-pptx, PyYAML, lxml, Pillow.
metadata:
  author: pptx-skills
  version: "1.0"
---

# Extract PPTX Template

Extract a clean template (masters/layouts/theme) from an existing pptx file, and generate a markdown skeleton documenting available layouts.

## When to Use

- User wants to extract a template from an existing pptx (e.g., "extract template", "提取模板")
- User wants to create a new template for slide generation
- User provides a pptx and wants to know what layouts are available

## Instructions

**Steps:**

1. Determine the input pptx file from the user's request. If not specified, look for the most recent `.pptx` file in the current directory.
2. Determine the output directory (default: `templates/`).
3. Run the extraction script:
   ```
   PYTHONPATH=<skill_root>/scripts python3 <skill_root>/scripts/extract_template.py <input.pptx> -o <output_dir>
   ```
   Replace `<skill_root>` with the absolute path to the pptx-skills installation directory.
4. Report:
   - Number of slide masters and layouts found
   - Which layouts were actually used in the source presentation
   - Placeholder information for each used layout
5. Show the generated `template.md` content to the user.

**Output files:**
- `<output_dir>/template.pptx` — Empty template preserving all masters, layouts, and themes
- `<output_dir>/template.md` — Markdown skeleton with layout documentation and examples

## Notes

- The extracted template.pptx is intentionally empty (no slides). It preserves only the slide masters, layouts, and theme definitions. This is by design — it serves as a reusable base for the `build-slides` skill.
- To verify the template is valid, open it in PowerPoint/WPS and check that layouts are available via "New Slide" → layout picker.
- For presentations with embedded charts, use `extract-charts` to also extract chart data as reusable ```` ```chart ```` blocks.
