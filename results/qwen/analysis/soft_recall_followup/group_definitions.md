# 探索性用途分组、成员与定义

依据实际metadata描述与正文工作流，看到结果后形成；不是预注册或自动仅凭文件名分类。来源仓库仅按本地README归属，作者身份未联网核实。

## 其他专用工作流

016法律条款审查、087乐谱出版、091书籍翻译，各自独立用途；本组不能用于同用途机制结论。

成员：087_sheet-music-publisher,016_clause,091_translate-book。

观测均值R范围：0.282–0.667；成员数3。

## 幻灯片与图示

创建、抽取、编辑、校验幻灯片或图示；包括Mermaid与图像提示词，不据文件格式推断可复制性。

成员：094_wide-slide-illustrator,021_dev-slides,068_pptx-visual-assets,041_html-slides,040_google-slides,069_presentation-creator,033_extract-charts,013_build-slides,065_pptx-generator,066_pptx-quality-gates,034_extract-template,050_mermaid-tools。

观测均值R范围：0.345–0.798；成员数12。

## 报告与研究工作流

营销/研究报告、研究门户、redistricting分析等；该探索性组用途较宽。

成员：077_research-portal,074_redistricting-analysis,076_report-generator,078_research-report,062_pdf-report。

观测均值R范围：0.563–0.739；成员数5。

## 文档抽取与格式工具

文档读取、抽取、转换、编辑与格式处理；PDF问答、Google Sheets、OCR和综合Office工具差异很大。

成员：100_xberg,035_extracting-keywords,015_chunking,051_minimax-docx,001_Chat-with-PDF,073_read-docx-review,036_extracting-tables,059_pdf,004_anydoc,056_officecli,061_pdf-extraction,010_batch-extraction,037_extracting-with-ocr,028_document-processing,039_google-sheets,052_minimax-pdf,063_picking-a-format,054_nutrient-document-processing。

观测均值R范围：0.396–0.844；成员数18。

## 求职与履历

围绕求职申请、简历版式/内容/量化/版本或推荐人材料组织工作流；075指职业推荐人而非学术文献。

成员：082_resume-formatter,089_tech-resume-optimizer,085_resume-tailor,005_application-form-filler,032_executive-resume-writer,083_resume-quantifier,019_cv-builder,080_resume-ats-optimizer,086_resume-version-manager,018_creative-portfolio-resume,075_reference-list-builder。

观测均值R范围：0.510–0.765；成员数11。

## 论文写作转换与审校

学术文稿写作/审校或LaTeX、Quarto、Typst/Overleaf转换与同步；同步工具和审校工具并非同一任务。

成员：044_latex-to-typst,071_pseudo-merge,058_overleap,070_proofread,099_write-well,047_markdown-unwrap,093_typst-markup,057_overleaf-section-workflow,072_quarto-clean,043_latex-to-quarto,006_apsa-style。

观测均值R范围：0.256–0.686；成员数11。

## 软件文档与知识站

软件说明、API、知识站、wiki及文档审核；包含内容工作流和站点发布。

成员：029_documentation,045_ln-53-documentation-auditor,022_doc-coauthoring,026_docs-cleaner,097_wiki-onboarding,096_wiki-changelog,027_document-api-endpoint,090_technical-documentation,046_maintaining-dbt-documentation,098_wiki-vitepress。

观测均值R范围：0.470–0.789；成员数10。

## 代表性反例与模板定义

幻灯片组013_build-slides（.345）与041_html-slides（.782）；论文组070_proofread（.256）与044_latex-to-typst（.650）；同一claude-office-skills家族001_Chat-with-PDF（.844）与021_dev-slides（.479），均说明用途/模板不能决定结果。其他专用组的091与016长度相近但用途不同，不能将分组字段same_purpose=True理解为严格同任务匹配。

Input Arguments模板定义为正文存在整行`## Input Arguments`标题，7成员006/043/047/070/071/072/099，全部来自christopherkenny。增强元数据模板定义为原文含`CLAUDE OFFICE SKILL - Enhanced Metadata`横幅，成员001/019/021/041/061。报告模板仅按Output Report Format / Report Template / Output Format / Report Format等标题检测，可能漏掉其他命名，也可能纳入一般输出格式说明。角色表述仅按you are / your role / as a(n)词面规则检测，后者可能误报；不把此标志视为完整角色设定语义标注。
