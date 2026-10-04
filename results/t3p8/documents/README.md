# t3p8 / documents 结果归档

日期：2026-10-03。范围：dataset=documents，train_num=3，prefix_length=8。

- [selecteddata 分析报告](selecteddata/analysis/实验结果分析.md)：9 组完整实验，固定 26 篇测试文档。
- [full data](full%20data/README.md)：未长度筛选的历史实验，包含完成记录、重复结果与未完成尝试。
- [selecteddata](selecteddata/README.md)：筛选后 36 篇数据的运行记录及日志。
- [文件清单与 SHA-256](archive_manifest.json)；[各次运行状态](run_inventory.json)。

采用复制归档，原 results/documents* 和 logs 文件保留。仅收录 train3 / prefix8 对应结果及配套清单、匹配日志；原文件内容不改动。原 JSON 内的 /root/... 路径是服务器来源路径，定位本机归档请使用清单的 archived 字段。未完成运行不计作零分实验，重复结果不当成独立重复。

selecteddata/analysis/summary.json 是本次统一的 9 次实验汇总。各 runs 目录内的旧 summary 仍是单次启动的局部汇总。

归档及分析可在原项目中使用 Python 3 重跑 selecteddata/analysis/archive_and_analyze.py；同名副本与源文件不一致时会停止，避免覆盖不同版本。分析脚本无外部依赖，不运行模型。
