---
name: extract-charts
description: Extract chart data from an existing PPTX file as markdown chart blocks. Use when the user wants to recreate or modify charts from an existing presentation, or to understand chart data in a PPTX file.
license: MIT
compatibility: Requires python-pptx.
metadata:
  author: pptx-skills
  version: "1.0"
---

# Extract Charts from PPTX

Extract chart data from an existing PowerPoint file and output as markdown ```` ```chart ```` blocks ready to paste into slide markdown.

## When to Use

- User wants to extract chart data from an existing PPTX (e.g., "extract charts", "提取图表数据")
- User wants to modify or recreate charts from an existing presentation
- User wants to understand what chart data a PPTX contains

## Instructions

**Steps:**

1. Determine the input pptx file from the user's request.
2. Run the extraction script:
   ```
   PYTHONPATH=<skill_root>/scripts python3 <skill_root>/scripts/extract_charts.py <input.pptx> [-o output.md]
   ```
   Replace `<skill_root>` with the absolute path to the pptx-skills installation directory.
3. Report:
   - Number of charts extracted
   - Which slides contained charts
4. Show the output to the user or save to file with `-o`.

**Output format:**

The output contains ```` ```chart ```` YAML blocks organized by slide, with comments indicating source slide and shape name. These blocks can be directly pasted into slide markdown for the `build-slides` skill.

## Notes

- Only charts with category data are extracted (column, bar, line, area, pie, doughnut, radar and their variants). XY scatter, bubble, and composite charts are skipped.
- Series names are preserved when available. Values are extracted as-is from the underlying Excel data.
- The extracted blocks are a starting point — users can modify values, titles, colors, and chart types before rebuilding.
