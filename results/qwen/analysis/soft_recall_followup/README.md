# 正文ROUGE后续分析交付

先读[中文完整报告](report_zh.md)。所有指标保持正式评估器定义，分析仅使用已经保存的本地数据，没有模型调用或重新训练。

## 主要文件

| 文件 | 统计单位与内容 |
|---|---|
| [逐输出诊断](diagnostics/output_diagnostics.csv) | 5670条；run_key+sample_index唯一；三指标、主类、多标签、锚点、停止状态、原文件定位 |
| [阅读审核记录](diagnostics/analyst_review.csv) | 56条实际阅读，初版/修订类别、判断与偏差；目的性分层抽查，不是独立人工金标准 |
| [逐Skill指标特征](skill_metrics_features_types.csv) | 70篇；三指标跨81次分布、结构、来源、模式与类型比例 |
| [Skill×配置](skill_config_metrics.csv) | 630单元；每单元9次，三指标均值/中位数/SD/排名 |
| [逐运行loss与表现](run_loss_metrics_types.csv) | 81运行；loss轨迹摘要、三指标、类型比例及低分分母 |
| [逐步loss](loss/loss_trajectories.csv) | 1813个current点，日志路径与行号 |
| [日志映射](loss/run_log_mapping.csv) | 短标识到长run_id、训练manifest、最终token IDs及评估路径 |
| [核验结果](delivery_validation.json) | 输出数量、指标一致、输入哈希、日志预算、链接与脚本校验 |

## 字段与分母

`run_key=t{train_num}_p{prefix_length}_s{sample_seed}_a{attack_seed}`，sample_index为0基测试顺序。JSONL行号为sample_index+1；原始CSV有多行字段，需按sample_index解析。

`body_rougeL_recall`为主指标；`body_rouge2_recall`、`body_rougeL_precision`为辅助指标。`primary_type`互斥，`labels`竖线分隔且可重叠。`type_*_n/rate`在运行表分母70、Skill表分母81；`type_*_low_n/low_rate`分母为对应实体的`n_low`（R<.2）。`label_*_rate`以全部70/81为分母，不能相加为100%。三指标和所有rate为0–1数值。

`anchors_json`为[reference_token_start,prediction_token_start,length]；`skip_intervals_json`为[reference_start,reference_end_exclusive,prediction_gap,missing_8gram_fraction]。这些是辅助匹配证据，不是ROUGE替代品。`budget_hit`与`ended_with_eos`可能重叠，`stop_state`优先EOS。`primary_type`为保守启发式，改写/无关/复杂循环保留不确定。

loss的`accepted_updates`为已接受替换数，`gradient_rounds`还含最终无改进轮；`candidate_upper_bound`只是候选数上界。`drop_std`为每步下降量的SD，非上下震荡。图表误差/区间解释见图注及报告。

特征定义及所有用途组成员见[group_definitions.md](group_definitions.md)。`starts_html_comment`等稀疏标志不可当一般规律。`mean_max_train_word_trigram_jaccard`每运行缺哈希不匹配的030训练文档，仅为已核验部分训练集相似性。词面特征的分词方式不用于结果指标。

## 复现

在项目根目录执行：

```bash
bash results/qwen/analysis/soft_recall_followup/run_analysis.sh
```

本机统计环境：`python3`，Python3.9，pandas2.3.3、numpy2.0.2、matplotlib3.9.4。固定tokenizer环境：`/private/tmp/qwen-no-cleanup-20261103/bin/python`，tokenizers0.21.1。tokenizer文件随既有项目位于`analysis/support/tokenizer/`，不下载模型。临时环境路径不是可移植依赖，可通过`STATS_PYTHON`与`TOKEN_PYTHON`指向已安装相同依赖的解释器。运行脚本只覆盖本次新增分析目录中的派生产物，不修改原始数据和既有分析。

脚本顺序：audit_metrics → analyze_overview → diagnostics/analyze_outputs → skills/analyze_skills → loss/analyze_loss → integrate_analysis → build_report → validate_delivery。`manual_review_sample.csv`保存初版72条抽查包；只有analyst_review.csv中的56条被计为完成阅读。阅读记录固化在integrate_analysis.py中，重跑不会伪装成新的人工审阅。

`review_texts.json`与`manual_review_packet.md`是本轮生成的定位辅助材料；完整内容仍以原始CSV/JSONL为准。主报告仅保留短证据。所有相关性、组别和阈值均为探索性；输入SHA256见input_hashes.json及loss/loss_validation.json。
