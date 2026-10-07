# documents · train3 · prefix8

更新日期：2026-10-07。仅保留完整实验：未筛选 **7/9** 组，筛选后 **9/9** 组。

- [全部结果分析](analysis/全部结果分析.md) · [完整实验表](analysis/all_results.csv) · [全部指标与均值](analysis/all_results.json)
- [未筛选结果](full%20data/README.md) · [筛选后结果](selecteddata/README.md)
- [筛选后详细分析](selecteddata/analysis/实验结果分析.md) · [筛选后 Excel 汇总](selecteddata/analysis/实验汇总.xlsx)
- [完整实验清单](run_inventory.json) · [原路径与文件校验清单](archive_manifest.json)

## 命名

保留原有 `full data`、`selecteddata` 及 `runs`、`logs`、`analysis` 子目录。

- seed 组合目录：例如 `full data/runs/s1a3/`，表示 `sample_seed=1`、`attack_seed=3`。相同组合的完整结果集中在同一个目录。
- `results.csv`：生成原文；`samples.json`：样本选择；`metrics.json`：汇总指标；`evaluation.json`：逐样本指标；`trigger_ids.json`：触发 token。
- `run.json`：完整配置、repeat_id、原启动时间与名称、原文件前缀和日志索引；`length_filter.json`：筛选清单（如有）。
- 原启动级汇总存放在各数据分组的 `analysis/launch_summaries/`，避免把覆盖多个 seed 的均值误当作单组指标。

共 16 个完整 seed 组合。已删除 13 条中断记录及专属日志，旧压缩包一并移除；1 份完全相同的完整副本已合并，两个原来源仍记录在对应 `run.json` 中。保留的原始实验文件内容未改写。

“完整”指生成 CSV 和汇总指标均已保存，不表示每篇测试文档都生成成功；失败样本记录保留。旧实验可能没有 `evaluation.json`，已有 CSV 和指标仍是完整结果。Excel 内的原运行名可通过 `archive_manifest.json` 和 `run.json` 对照。

需要重新核验和刷新汇总时，运行 `python3 results/t3p8/documents/organize_results.py`。脚本只读取当前归档，不运行模型。
