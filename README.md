# PLeak Skill 实验

基于 PLEAK 的 Skill 文本泄漏实验。代码、源数据和各批结果集中保留，结果入口如下。

| 实验批次 | 内容 | 入口 |
| --- | --- | --- |
| Qwen3 documents | train=3/4/5 × prefix=8/16/32，共 81 次正式主结果；报告、重评数据和图表已统一整理 | [实验结果总报告](results/qwen/README.md) · [Excel 汇总](results/qwen/Qwen3_documents_重算指标.xlsx) |
| Llama documents | train=3、prefix=8；未筛选与筛选后各 9 次 | [结果说明](results/llama/documents/README.md) · [两组对照](results/llama/documents/analysis/fulldata_vs_selecteddata_对照分析.md) |
| 早期实验 | Web/Webtesting、Samples 及手工工作簿 | [历史实验](results/history/README.md) |

完整导航见 [实验结果目录](results/README.md)。历史分析与旧 Excel 可能采用早期指标口径，当前统计应核对各批原始指标和补评 JSON。

## 目录

```text
main.py / Attack.py / Sampler.py    实验入口、训练与生成评估
DataFactory.py / ModelFactory.py   数据与模型加载
Defense.py / util/                 运行依赖与指标工具
data/                             原始数据与来源压缩包
results/                          qwen / llama / history
reports/                          研究记录、配置审查与诊断资料
scripts/                          保留的 GPU 容量检查工具
tests/                            模型和指标回归测试
docs/                             完整使用说明与本次清理记录
environment.yaml                  环境依赖
```

## 运行与复核

在项目根目录运行。环境安装、模型配置、参数和指标解释见 [使用说明](docs/usage.md)。

```bash
# 单次 Qwen 实验；新运行会创建独立目录，不覆盖已归档结果
python -u main.py documents 12 qwen3 qwen3 3 \
  --prefix-lengths 8 --sample-seeds 0 --attack-seeds 1

# 只核对归档结果，不加载模型
python results/qwen/organize_results.py --check

# 指标回归测试
python -m unittest discover -s tests -p 'test_overlap_metrics.py' -v
```

本次整理保留了全部源数据与原始实验记录，清理范围见 [2026-11-03 清理记录](docs/cleanup_20261103.md)。
