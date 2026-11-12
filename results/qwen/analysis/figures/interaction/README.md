# 训练文档数 × 监督前缀：描述性交互图

- [双向交互作用图](factor_interaction.png) · [SVG](factor_interaction.svg)：行是完整前缀 ASR、正文 ROUGE-L Recall；左列横轴为训练文档数，右列为监督前缀长度。
- [条件变化幅度图](conditional_changes.png) · [SVG](conditional_changes.svg)：显示相邻已测试参数值之间的指标增减，单位为百分点。同一行正负号不同直接表示效果方向随另一参数改变。
- [绘图数据及变化幅度](plot_data.json)

每个配置采用冻结的 9 次正式主运行，共 630 条测试记录。ASR 为完整前缀成功数/630；Recall 为记录均值。没有混入被替代尝试。

正文 Recall 的例子：prefix_length=32 时，train_num=3→4→5 为 61.14%→50.73%→61.16%；prefix_length=16→32 时，train_num=3 上升 7.83 个百分点，train_num=4 下降 10.13 个百分点，train_num=5 下降 5.11 个百分点。

ASR 的例子：prefix_length=8 时，train_num=3→4→5 为 3.97%→10.63%→7.94%；prefix_length=8→16 时，train_num=3 上升 0.48 个百分点，train_num=4 下降 2.38 个百分点，train_num=5 不变。

合适表述：在已测试网格内，增加训练文档数或延长监督前缀，并未带来一致的单调提升；变化的方向和幅度取决于另一参数的取值。这是对配置均值的描述，不等于所有固定参数条件下均非单调，也不声称统计显著的交互效应。seed 对共用测试文档，不能直接把 630 条记录视为独立实验。

复现：`python3 scripts/plot_qwen_interaction.py`。
