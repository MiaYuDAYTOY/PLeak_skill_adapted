"""Verify complete experiments grouped by seeds and rebuild their indexes.

Run with Python 3 from any directory. Raw result files are read-only. Former
paths are retained in archive_manifest.json and each launch's run.json.
"""
from pathlib import Path
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from datetime import date

BASE = Path(__file__).resolve().parent
CATEGORIES = ("full data", "selecteddata")
LABELS = {"full data": "未筛选", "selecteddata": "筛选后"}
DIAGNOSTICS = ("empty_content_count", "empty_content_rate", "body_rougeL_ge_0_5_count",
               "body_rougeL_ge_0_9_count", "median_prediction_tokens")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(path):
    return str(path.relative_to(BASE))


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |",
                      "| " + " | ".join(["---"] * len(headers)) + " |"] +
                     ["| " + " | ".join(map(str, row)) + " |" for row in rows])


def percent(value):
    return "—" if value is None else f"{value * 100:.2f}%"


def link(path):
    return path.replace(" ", "%20")


def verify_manifest():
    manifest = read(BASE / "archive_manifest.json")
    verified = set()
    for record in manifest["files"]:
        key = record["archived"]
        path = BASE / record["archived"]
        content = path.read_bytes()
        assert len(content) == record["bytes"], key
        assert hashlib.sha256(content).hexdigest() == record["sha256"], key
        verified.add(key)
    return len(manifest["files"]), len(verified)


def collect():
    attempts, launch_count, checked_summaries = [], 0, 0
    for category in CATEGORIES:
        for folder in sorted((BASE / category / "runs").iterdir()):
            if not folder.is_dir():
                continue
            launch_count += 1
            launch = read(folder / "run.json")
            selections = sorted(folder.glob("samples.json"))
            assert len(selections) == 1, f"Missing sample selection: {folder}"
            for filename in ("results.csv", "metrics.json", "trigger_ids.json"):
                assert (folder / filename).is_file(), f"Incomplete experiment: {folder / filename}"
            for path in selections:
                selection = read(path)
                assert folder.name == f"s{selection['sample_seed']}a{selection['attack_seed']}"
                assert launch["configuration"] == {k: v for k, v in selection.items() if k not in ("train_samples", "test_samples")}
                assert (selection["dataset"], selection["train_num"], selection["prefix_length"]) == ("documents", 3, 8)
                record = {"category": category, "run_id": folder.name,
                          "repeat_id": selection["repeat_id"], "sample_seed": selection["sample_seed"],
                          "attack_seed": selection["attack_seed"], "source_run": folder.name,
                          "source_selection": rel(path), "source_config": rel(folder / "run.json"),
                          "source_launches": [o["run_id"] for o in launch["origins"]],
                          "test_num": selection["test_num"],
                          "train_pool_size": selection["train_pool_size"],
                          "train_documents": [Path(s["path"]).parent.name for s in selection["train_samples"]],
                          "test_documents": [Path(s["path"]).parent.name for s in selection["test_samples"]],
                          "excluded_before_evaluation": selection.get("test_selection", {}).get("excluded_test_num", 0)}
                metric_path = folder / "metrics.json"
                if metric_path.exists():
                    metadata = read(metric_path)
                    metrics = metadata["metrics"]
                    for key in ("dataset", "train_num", "prefix_length", "repeat_id", "sample_seed", "attack_seed", "test_num"):
                        assert metadata[key] == selection[key], (metric_path, key)
                    csv_path = folder / "results.csv"
                    with csv_path.open(encoding="utf-8", newline="") as f:
                        rows = list(csv.DictReader(f))
                    assert len(rows) == len(selection["test_samples"]) == metrics["total_samples"]
                    assert sum(row.get("status", "ok") == "ok" for row in rows) == metrics["evaluated_samples"]
                    assert metrics["failed_samples"] == metrics["total_samples"] - metrics["evaluated_samples"]
                    failed = []
                    for row, sample in zip(rows, selection["test_samples"]):
                        assert hashlib.sha256(row["context"].encode()).hexdigest() == sample["content_sha256"]
                        if row.get("sample_path"):
                            assert row["sample_path"] == sample["path"]
                            assert int(row["sample_index"]) == sample["pool_index"]
                        if row.get("status", "ok") != "ok":
                            failed.append(Path(sample["path"]).parent.name)
                    evaluation_path = folder / "evaluation.json"
                    diagnostics = {}
                    if evaluation_path.exists():
                        evaluation = read(evaluation_path)
                        assert evaluation["metrics"] == metrics
                        samples = evaluation["samples"]
                        assert len(samples) == metrics["evaluated_samples"]
                        assert sum(s["full_skill_prefix"] for s in samples) == metrics["full_skill_leak_count"]
                        fields = {"full_skill_leak_rate": "full_skill_prefix", "exact_markdown_match_rate": "exact_markdown_match",
                                  "exact_token_match_rate": "exact_token_match", "eos_rate": "ended_with_eos"}
                        for name, value in metrics.items():
                            if name.startswith("mean_") or name in fields:
                                field = fields.get(name, name.removeprefix("mean_"))
                                assert math.isclose(value, statistics.mean(float(s[field]) for s in samples), abs_tol=1e-12)
                        diagnostics = {"empty_content_count": sum(s["prediction_token_count"] == 0 for s in samples),
                                       "body_rougeL_ge_0_5_count": sum(s["body_rougeL_recall"] >= .5 for s in samples),
                                       "body_rougeL_ge_0_9_count": sum(s["body_rougeL_recall"] >= .9 for s in samples),
                                       "median_prediction_tokens": statistics.median(s["prediction_token_count"] for s in samples)}
                        diagnostics["empty_content_rate"] = diagnostics["empty_content_count"] / len(samples)
                    record.update({"status": "complete_current_metrics" if "mean_body_rougeL_recall" in metrics else "complete_legacy_metrics",
                                   "source_metrics": rel(metric_path), "source_csv": rel(csv_path),
                                   "source_evaluation": rel(evaluation_path) if evaluation_path.exists() else None,
                                   "metrics": metrics, "diagnostics": diagnostics, "failed_documents": failed,
                                   "fingerprint": {name: sha(folder / name) for name in
                                                   ("results.csv", "samples.json", "metrics.json", "trigger_ids.json")}})
                attempts.append(record)
        for summary_path in sorted((BASE / category / "analysis/launch_summaries").glob("*.json")):
            summary = read(summary_path)
            launch_metrics = [r["metrics"] for r in attempts if r["category"] == category and summary_path.stem in r["source_launches"]]
            assert summary["overall_mean"]["run_count"] == len(launch_metrics)
            for key, value in summary["overall_mean"]["metric_means"].items():
                assert math.isclose(value, statistics.mean(m[key] for m in launch_metrics), abs_tol=1e-12)
            checked_summaries += 1
    return attempts, launch_count, checked_summaries


def main():
    csv.field_size_limit(100_000_000)
    source_count, verified_count = verify_manifest()
    attempts, launch_count, checked_summaries = collect()
    candidates = defaultdict(list)
    for record in attempts:
        if "metrics" in record:
            candidates[(record["category"], record["sample_seed"], record["attack_seed"])].append(record)
    canonical, duplicates = [], []
    for key, records in sorted(candidates.items()):
        preferred = min(records, key=lambda r: (not bool(r["source_evaluation"]), r["run_id"]))
        for record in records:
            if record is preferred:
                continue
            assert record["fingerprint"] == preferred["fingerprint"], f"Different completed results share seeds {key}; review before combining"
            record["status"] = "exact_duplicate"
            record["duplicate_of"] = preferred["source_metrics"]
            duplicates.append(record)
        canonical.append(preferred)
    metric_fields = list(dict.fromkeys(k for r in canonical for k in r["metrics"]))
    grid = []
    for category in CATEGORIES:
        for sample in range(3):
            for attack in (1, 2, 3):
                grid.append(next((r for r in canonical if (r["category"], r["sample_seed"], r["attack_seed"]) ==
                                  (category, sample, attack)),
                                 {"category": category, "sample_seed": sample, "attack_seed": attack,
                                  "status": "missing_completed_result", "metrics": {}, "diagnostics": {}}))

    def aggregate(records):
        values = [{**r["metrics"], **r["diagnostics"]} for r in records]
        fields = metric_fields + list(DIAGNOSTICS)
        return {"run_count": len(records),
                "metric_means": {k: statistics.mean(v[k] for v in values) if values and all(k in v for v in values) else None for k in fields},
                "metric_coverage": {k: sum(k in v for v in values) for k in fields}}

    groups = {}
    for category in CATEGORIES:
        records = [r for r in canonical if r["category"] == category]
        groups[category] = {"overall": aggregate(records),
                            "sample_seed": {str(s): aggregate([r for r in records if r["sample_seed"] == s]) for s in range(3)},
                            "attack_seed": {str(a): aggregate([r for r in records if r["attack_seed"] == a]) for a in (1, 2, 3)}}
    cleanup = read(BASE / "archive_manifest.json")["cleanup"]
    audit = {"as_of": date.today().isoformat(), "mode": "complete experiments only; grouped by sample_seed and attack_seed",
             "seed_directories": launch_count, "source_records_verified": source_count,
             "archived_files_verified": verified_count, "launch_summaries_verified": checked_summaries,
             "unique_completed_runs": len(canonical), "retained_incomplete_runs": 0, "cleanup": cleanup,
             "missing_seed_combinations": [{k: r[k] for k in ("category", "sample_seed", "attack_seed")} for r in grid if r["status"] == "missing_completed_result"],
             "old_metrics_not_reevaluated": "No model or tokenizer was run. Missing metrics remain null, never zero.",
             "aggregation": "Equal weight over unique completed experiments in each category. A mean is null if any included experiment lacks that metric."}
    analysis = BASE / "analysis"
    write(BASE / "run_inventory.json", attempts)
    write(analysis / "all_results.json", {"audit": audit, "runs": canonical, "groups": groups})
    with (analysis / "all_results.csv").open("w", encoding="utf-8-sig", newline="") as f:
        columns = ["category", "sample_seed", "attack_seed", "repeat_id", "run_id", "status", "train_pool_size", "test_num",
                   "excluded_before_evaluation", *metric_fields, *DIAGNOSTICS, "source_metrics"]
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for record in canonical:
            flat = {**record, **record["metrics"], **record["diagnostics"]}
            writer.writerow({k: flat.get(k, "") for k in columns})
    complete_counts = {c: groups[c]["overall"]["run_count"] for c in CATEGORIES}
    status_names = {"complete_current_metrics": "完整·新指标", "complete_legacy_metrics": "完整·旧指标", "missing_completed_result": "缺少结果"}
    report = ["# documents 全部实验结果", f"更新日期：{audit['as_of']}。train_num=3，prefix_length=8，trigger token_length=12，shadow/target=llama。",
              table(["数据范围", "完整组合", "新指标", "旧指标", "缺少组合"],
                    [[LABELS[c], f"{complete_counts[c]}/9", sum(r['category'] == c and r['status'] == 'complete_current_metrics' for r in canonical),
                      sum(r['category'] == c and r['status'] == 'complete_legacy_metrics' for r in canonical), 9 - complete_counts[c]] for c in CATEGORIES]),
              f"仅保留 {len(canonical)} 组完整结果，分别按 s{{sample_seed}}a{{attack_seed}} 归组。已删除 {cleanup['removed_incomplete_experiments']} 条中断记录、{cleanup['removed_incomplete_only_logs']} 份仅关联中断尝试的日志，并合并 {cleanup['merged_identical_complete_copies']} 份完全相同的重复结果。",
              "## 完整实验", table(["数据范围", "sample", "attack", "状态", "成功/总数", "完整泄漏率", "Token recall", "正文 RL recall", "来源"],
                [[LABELS[r['category']], r['sample_seed'], r['attack_seed'], status_names[r['status']],
                  f"{r['metrics'].get('evaluated_samples', '—')}/{r['metrics'].get('total_samples', '—')}",
                  percent(r['metrics'].get('full_skill_leak_rate')), percent(r['metrics'].get('mean_token_recall')),
                  percent(r['metrics'].get('mean_body_rougeL_recall')),
                  f"[{r['run_id']}](../{link(r['source_metrics'])})"] for r in canonical]),
              "## 总体均值", "对各数据范围内的完整实验等权平均；任一纳入实验缺少某指标，该指标总体均值留空（—），不以 0 代替。不同训练池、测试集合及失败分母之间只作描述性汇总。",
              table(["指标", f"未筛选（{complete_counts['full data']} 组）", f"筛选后（{complete_counts['selecteddata']} 组）"],
                    [[label, *[percent(groups[c]['overall']['metric_means'][key]) for c in CATEGORIES]] for key, label in
                     [('full_skill_leak_rate', '完整原文前缀泄漏率'), ('mean_token_recall', 'Token recall'), ('mean_token_precision', 'Token precision'),
                      ('mean_common_prefix_ratio', '公共前缀比例'), ('mean_body_rougeL_recall', '正文 ROUGE-L recall'), ('mean_body_rouge2_recall', '正文 ROUGE-2 recall')]]),
              "## 必要说明",
              "- 完整实验指已经保存生成 CSV 和汇总指标，允许部分测试样本生成失败；这些失败行及统计均保留。未筛选缺少 s2a2、s2a3，不为缺失组合建立空目录。",
              "- 未筛选旧五组各尝试 70 篇、成功 64 篇；10 月 5 日 (1,3) 尝试 64 篇、成功 51 篇、失败 13 篇；10 月 7 日 (2,1) 尝试 64 篇、成功 49 篇、失败 15 篇。重合指标使用成功样本分母。",
              "- 10 月 7 日训练池由 30 篇缩为 29 篇，并排除 009_baoyu-slide-deck；同一 sample_seed 跨版本不保证抽到相同文档。训练文档、测试文档和失败文档均列在逐次清单中。",
              "- selecteddata 九组使用同一固定 26 篇测试集。完整泄漏为 4/234（1.71%）；234 为文档×seed 观测次数，并非 234 篇独立文档。",
              "- 旧五组没有新增 ROUGE 指标，本次仅校验现有结果，未加载模型或 tokenizer 补评。原始 JSON、CSV、日志中的服务器路径作为来源信息保留；本机定位使用 source_* 和 archived 字段。",
              "[完整指标与分组均值](all_results.json) · [完整实验 CSV](all_results.csv) · [完整实验清单](../run_inventory.json) · [原路径与 SHA-256 映射](../archive_manifest.json)。"]
    (analysis / "全部结果分析.md").write_text("\n\n".join(report) + "\n", encoding="utf-8")
    readme = f"""# documents · train3 · prefix8

更新日期：{audit['as_of']}。仅保留完整实验：未筛选 **{complete_counts['full data']}/9** 组，筛选后 **{complete_counts['selecteddata']}/9** 组。

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

共 {len(canonical)} 个完整 seed 组合。已删除 {cleanup['removed_incomplete_experiments']} 条中断记录及专属日志，旧压缩包一并移除；{cleanup['merged_identical_complete_copies']} 份完全相同的完整副本已合并，两个原来源仍记录在对应 `run.json` 中。保留的原始实验文件内容未改写。

“完整”指生成 CSV 和汇总指标均已保存，不表示每篇测试文档都生成成功；失败样本记录保留。旧实验可能没有 `evaluation.json`，已有 CSV 和指标仍是完整结果。Excel 内的原运行名可通过 `archive_manifest.json` 和 `run.json` 对照。

需要重新核验和刷新汇总时，运行 `python3 results/t3p8/documents/organize_results.py`。脚本只读取当前归档，不运行模型。
"""
    (BASE / "README.md").write_text(readme, encoding="utf-8")
    for category in CATEGORIES:
        records = [r for r in attempts if r["category"] == category]
        lines = [f"# {LABELS[category]} · documents · train3 · prefix8",
                 f"完整且去重 {complete_counts[category]}/9 组。[全部结果分析](../analysis/全部结果分析.md) · [完整实验清单](../run_inventory.json)。",
                 table(["seed 组合", "sample_seed", "attack_seed", "生成结果", "评估指标", "配置与来源"],
                       [[r['run_id'], r['sample_seed'], r['attack_seed'],
                         f"[CSV](runs/{r['run_id']}/results.csv)", f"[JSON](runs/{r['run_id']}/metrics.json)",
                         f"[run.json](runs/{r['run_id']}/run.json)"] for r in records])]
        if category == "selecteddata":
            lines.append("[九次实验详细分析](analysis/实验结果分析.md) · [实验汇总 Excel](analysis/实验汇总.xlsx)。")
        (BASE / category / "README.md").write_text("\n\n".join(lines) + "\n", encoding="utf-8")
    write(analysis / "validation.json", {"status": "passed", **audit})
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
