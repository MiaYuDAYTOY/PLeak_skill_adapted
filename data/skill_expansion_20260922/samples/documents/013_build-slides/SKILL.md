---
name: build-slides
description: Build a PPTX presentation from Markdown content using an extracted template. Supports text, bullet lists, tables, images, blockquotes, mermaid diagrams, and native Excel charts. Use when the user wants to generate slides from markdown or create a presentation.
license: MIT
compatibility: Requires python-pptx, PyYAML, lxml, Pillow. Optional mermaid-cli (npx @mermaid-js/mermaid-cli) for diagram rendering.
metadata:
  author: pptx-skills
  version: "1.1"
---

# Build PPTX from Markdown

Build a polished PPTX presentation from a Markdown file and a template extracted by the `extract-template` skill.

## When to Use

- User wants to generate a pptx from markdown (e.g., "build slides", "生成幻灯片")
- User asks to create or update a presentation
- User has a markdown file with slide content and a template.pptx

## Instructions

**Steps:**

1. Ensure a template exists. If not, suggest running `extract-template` first.
2. Help the user write or review their markdown file (see format below).
3. Run the build script:
   ```
   PYTHONPATH=<skill_root>/scripts python3 <skill_root>/scripts/build_slides.py <input.md> [-t template.pptx] [-o output.pptx] [--img-dir slides-img]
   ```
   Replace `<skill_root>` with the absolute path to the pptx-skills installation directory.
4. Report the number of slides generated and output file path.

## Markdown Format

### Front Matter (YAML)

```yaml
---
title: "Presentation Title"
subtitle: "Subtitle text"
template: "templates/template.pptx"
---
```

- `title` / `subtitle`: Shown on the title slide. Subtitle supports `\n` for newlines.
- `template`: Path to the template pptx (from `extract-template`).
- `output`: (Optional) Output path. Defaults to `<input-name>.pptx`.

### Slide Syntax

- `## Heading` — Slide title
- `---` — Slide separator
- `<!-- layout: xxx -->` — Specify layout (see Layout Control below)

### Layout Control

You can control slide layouts in three ways:

**1. Standard Layout Aliases (Recommended)**

Use semantic layout names that work across any template:

```markdown
## My Slide
<!-- layout: standard -->
```

**Standard Layout Types:**

| Type | Alias | Description | Use Case |
|------|-------|-------------|----------|
| **Structural Layouts** | | | |
| cover | title-slide, 封面 | Title slide | Presentation opening |
| toc | contents, agenda, 目录 | Table of contents | Chapter overview |
| section | chapter, 章节 | Section divider | New chapter marker |
| summary | conclusion, 总结 | Summary slide | Presentation ending |
| **Content Layouts** | | | |
| standard | title-content, 标准 | Title + body | Most common (default) |
| two-column | two-content, 双栏 | Left/right columns | Comparison, side-by-side |
| image | picture, 图片 | Image display | Screenshots, diagrams |
| chart | graph, 图表 | Chart display | Data visualization |
| table | 表格 | Table display | Data comparison |
| mixed | hybrid, 混合 | Text + chart mix | Combined content |
| title-only | blank, free, 仅标题 | Free layout | Custom positioning |

> **section 页注意**：body 内容会填入副标题占位符，空间有限。只写一句简短的章节描述（≤20 字），不要放完整的正文内容，否则会溢出。

**2. Layout Index**

Use the numeric index from the template:

```markdown
## My Slide
<!-- layout: 7 -->
```

**3. Template Layout Name**

Use the exact layout name from the template:

```markdown
## My Slide
<!-- layout: Title and Content -->
```

**Finding Available Layouts**

List all layouts in your template:

```bash
PYTHONPATH=<skill_root>/scripts python3 <skill_root>/scripts/list_layouts.py template.pptx
```

This shows:
- Layout index numbers
- Layout names
- Recommended standard aliases
- Placeholder information

### Supported Content

| Element | Syntax | Notes |
|---------|--------|-------|
| Bullet list | `- item` / `  - sub-item` | Indent with 2 spaces per level |
| Bold/Italic | `**bold**` / `*italic*` | Inline formatting |
| Table | Standard markdown table | Centered text, auto-sized |
| Image | `![alt](path)` | Auto-scaled to fit |
| Blockquote | `> text` | Mapped to caption area |
| Mermaid | ` ```mermaid ` code block | Rendered to PNG via mermaid-cli |
| Chart | ` ```chart ` YAML block | Native Excel chart (see Chart Blocks below) |

### Layout Auto-Selection

When no layout is specified, the script automatically selects the best layout based on content:

| Content Pattern | Layout Selected | Reason |
|----------------|-----------------|--------|
| Chart + text or table | mixed | Charts on right, text/table on left |
| Has chart(s) only | chart (Title Only) | Charts need free positioning |
| Image only (no text, no table) | image | Optimized for visual display |
| Blockquote, or text + image | two-column | Left/right comparison |
| Table only (no text) | table | Table-optimized layout |
| Empty body | title-only | Free layout for custom content |
| Default | standard | Most common content type |

**Override auto-selection** with `<!-- layout: xxx -->` on any slide.

### Chart Blocks

Embed native Excel charts using fenced YAML blocks:

```yaml
# inside a ```chart block
type: column          # column | column-stacked | column-stacked-100
                      # bar | bar-stacked | bar-stacked-100
                      # line | line-stacked | line-stacked-100
                      # area | area-stacked | area-stacked-100
                      # pie | pie-exploded | doughnut | doughnut-exploded
                      # radar | radar-filled
                      # scatter | bubble | waterfall | combo
title: "Chart Title"
categories: [A, B, C]
series:
  - name: "Series 1"
    values: [10, 20, 30]
    color: "#C00000"  # optional hex color
  - name: "Series 2"
    values: [15, 25, 35]
position: center      # left | right | center (default: center)
width: "60%"          # percentage of slide width (default: 60%)
labels: true          # show data labels (default: true)
number_format: "0.0"  # number format for labels (optional)
```

Charts are embedded as native Excel objects — double-click in PowerPoint to edit data.

**Note on percentage format:** When using `number_format: "0.0%"`, values must be decimals (e.g., `0.243` displays as `24.3%`). This follows Excel conventions.

#### Multiple Charts

Multiple chart blocks on one slide are auto-arranged:
- 2 charts: side by side
- 3+ charts: 2-column grid

#### Chart + Table/Text

When a slide has both text/tables and charts, content is split:
- Text and tables on the left half
- Charts on the right half

## Example

See [examples/demo.md](../examples/demo.md) for a complete example.
