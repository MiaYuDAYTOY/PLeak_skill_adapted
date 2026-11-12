# 实验结果目录

| 批次 | 实验范围 | 主要入口 |
| --- | --- | --- |
| [Qwen3 documents](qwen/README.md) | 正式 test70 共 81 次主结果；报告、重评数据和图表已统一整理 | [实验结果总报告](qwen/README.md) · [Excel](qwen/Qwen3_documents_重算指标.xlsx) · [配置汇总](qwen/analysis/data/summary.csv) |
| [Llama documents](llama/documents/README.md) | train3 / prefix8；full data、selecteddata 各 9 次 | [未筛选 Excel](llama/documents/full%20data/analysis/fulldata实验汇总.xlsx) · [筛选后 Excel](llama/documents/selecteddata/analysis/selecteddata实验汇总.xlsx) · [对照分析](llama/documents/analysis/fulldata_vs_selecteddata_对照分析.md) |
| [早期实验](history/README.md) | Web/Webtesting、Samples、手工记录 | [Web 结果](history/web/runs/) · [Samples](history/samples/) |

每批的原始输出、配置、日志及统计工具放在同一目录。Qwen 中的历史筛选、冒烟、未完成及被替换结果仍保留，并由清单明确标记，不混入正式汇总。

Llama 旧导出表保存在 [历史快照](llama/documents/archive/)，筛选后指标定义见 [指标定义工作簿](llama/documents/selecteddata/analysis/指标定义.xlsx)。旧表与历史 Markdown 的指标口径可能早于后续补评，以对应原始指标、补评 JSON 和对照数据为准。

`samples`、`metrics`、`evaluation` 等原始文件中的旧绝对路径作为运行来源保留。实际文件位置由各批归档清单解析；本次目录迁移见 [清理记录](../docs/cleanup_20261103.md)。
