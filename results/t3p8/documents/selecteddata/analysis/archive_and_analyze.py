"""Archive documents/train3/prefix8 and audit existing evaluation JSON; no model runs.

Run from anywhere with Python 3. Standard library only. Original files are copied,
never moved or overwritten. Conflicting archive copies stop the operation.
"""
from pathlib import Path
import collections
import hashlib
import json
import math
import random
import shutil
import statistics as stats

HERE = Path(__file__).resolve().parent
DOCS = HERE.parents[1]
ROOT = DOCS.parents[2]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def short(path):
    return Path(path).parent.name


def identity(sample):
    return (short(sample["path"]), sample["content_sha256"])


def pct(value):
    return f"{value * 100:.2f}%"


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |"] + ["| " + " | ".join(map(str, row)) + " |" for row in rows])


def main():
    files, inventory, metric_hashes = [], [], {}
    logs = [(p, p.read_text(errors="replace")) for p in sorted((ROOT / "logs").glob("*.log"))]

    def copy(src, dst):
        sha = digest(src)
        if dst.exists() and digest(dst) != sha:
            raise ValueError(f"Archive conflicts with source: {dst}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        assert digest(dst) == sha
        files.append({"source": str(src.relative_to(ROOT)), "archived": str(dst.relative_to(DOCS)), "bytes": src.stat().st_size, "sha256": sha})

    for run_dir in sorted((ROOT / "results").glob("documents*")):
        sample_files = sorted(run_dir.glob("*train3_*prefix8*.samples.json"))
        if not sample_files:
            continue
        metadata = [read(p) for p in sample_files]
        assert all(d["dataset"] == "documents" and d["train_num"] == 3 and d["prefix_length"] == 8 for d in metadata)
        selected = all(d.get("test_selection", {}).get("length_filter", {}).get("policy") == "pre_split_length_filter_v1" for d in metadata)
        category = "selecteddata" if selected else "full data"
        assert all(d["test_num"] == (26 if selected else 70) for d in metadata)
        dest = DOCS / category / "runs" / run_dir.name
        included = [p for p in sorted(run_dir.iterdir()) if p.is_file() and (("_train3_" in p.name and "_prefix8" in p.name) or p.name == "length_filter.json")]
        for p in included:
            copy(p, dest / p.name)
        matching_logs = [p for p, text in logs if run_dir.name in text]
        for p in matching_logs:
            copy(p, DOCS / category / "logs" / p.name)
        statuses = []
        for p, d in zip(sample_files, metadata):
            metric = p.with_name(p.name.replace(".samples.json",
        ".metrics.json"))
            status = "evaluated" if metric.exists() else "selection_only_no_metrics"
            record = {"sample_seed": d["sample_seed"], "attack_seed": d["attack_seed"], "status": status}
            if metric.exists():
                sha = digest(metric)
                if sha in metric_hashes:
                    record["identical_metrics_to"] = metric_hashes[sha]
                else:
                    metric_hashes[sha] = str(metric.relative_to(ROOT))
            statuses.append(record)
        inventory.append({"source": str(run_dir.relative_to(ROOT)), "category": category, "archived": str(dest.relative_to(DOCS)), "files": len(included), "logs": [p.name for p in matching_logs], "experiments": statuses})

    write(DOCS / "archive_manifest.json", {"archive_date": "2026-10-03",
        "mode": "copy_originals_preserved",
        "scope": {"dataset": "documents",
        "train_num": 3, "prefix_length": 8}, "files": files})
    write(DOCS / "run_inventory.json", inventory)

    runs, selections, all_samples, full_cases = [], {}, [], []
    test_identity = filter_identity = None
    checks = collections.Counter()
    field_map = {"full_skill_leak_rate": "full_skill_prefix",
        "exact_markdown_match_rate": "exact_markdown_match",
        "exact_token_match_rate": "exact_token_match",
        "eos_rate": "ended_with_eos"}
    for path in sorted((DOCS / "selecteddata" / "runs").glob("*/*.evaluation.json")):
        d = read(path)
        m, ss = d["metrics"], d["samples"]
        key = (d["sample_seed"], d["attack_seed"])
        assert key not in selections, f"Duplicate selecteddata experiment: {key}"
        selection = read(path.with_name(path.name.replace(".evaluation.json",
        ".samples.json")))
        selections[key] = selection
        metric = read(path.with_name(path.name.replace(".evaluation.json",
        ".metrics.json")))
        assert {k: v for k, v in d.items() if k != "samples"} == metric
        assert m["total_samples"] == m["evaluated_samples"] == len(ss) == 26
        assert m["failed_samples"] == 0
        assert len({s["index"] for s in ss}) == 26
        assert m["full_skill_leak_count"] == sum(s["full_skill_prefix"] for s in ss)
        for name, value in m.items():
            if name.startswith("mean_") or name in field_map:
                field = field_map.get(name, name.removeprefix("mean_"))
                assert math.isclose(value, stats.mean(float(s[field]) for s in ss), abs_tol=1e-12)
                checks["aggregate_metrics_recomputed"] += 1
        ids = [identity(s) for s in selection["test_samples"]]
        if test_identity is None:
            test_identity = ids
        assert ids == test_identity
        for sample, source in zip(ss, selection["test_samples"]):
            assert short(sample["sample_path"]) == short(source["path"])
            assert sample["index"] == source["pool_index"]
            for k, v in sample.items():
                if k.endswith(("recall",
        "precision",
        "ratio")):
                    assert math.isfinite(v) and 0 <= v <= 1
        assert len(selection["train_samples"]) == 3 and selection["train_pool_size"] == 10
        assert not (set(identity(s) for s in selection["train_samples"]) & set(ids))
        assert not ({s["content_sha256"] for s in selection["train_samples"]} & {h for _, h in ids})
        filt = read(path.parent / "length_filter.json")
        norm_filter = {k: v for k, v in filt.items() if k != "manifest_path"}
        if filter_identity is None:
            filter_identity = norm_filter
        assert norm_filter == filter_identity
        assert (filt["source_count"], filt["kept_count"], filt["excluded_count"]) == (100, 36, 64)
        shuffled = sorted(filt["kept_samples"], key=lambda s: s["path"])
        random.Random(0).shuffle(shuffled)
        assert [identity(s) for s in shuffled[10:]] == ids
        picked = random.Random(d["sample_seed"]).sample(shuffled[:10], 3)
        assert [identity(s) for s in picked] == [identity(s) for s in selection["train_samples"]]
        empty = sum(s["prediction_token_count"] == 0 for s in ss)
        extra = {"empty_content_count": empty, "body_rougeL_ge_0_5_count": sum(s["body_rougeL_recall"] >= .5 for s in ss), "body_rougeL_ge_0_9_count": sum(s["body_rougeL_recall"] >= .9 for s in ss), "median_prediction_tokens": stats.median(s["prediction_token_count"] for s in ss)}
        run = {"sample_seed": key[0], "attack_seed": key[1], "source": str(path.relative_to(DOCS)), "metrics": m, "diagnostics": extra}
        runs.append(run)
        for s in ss:
            row = {"sample_seed": key[0], "attack_seed": key[1], "document": short(s["sample_path"]), **s}
            all_samples.append(row)
            if s["full_skill_prefix"]:
                full_cases.append(row)
        checks["completed_runs_checked"] += 1
    runs.sort(key=lambda r: (r["sample_seed"], r["attack_seed"]))
    assert set(selections) == {(s, a) for s in range(3) for a in (1, 2, 3)}
    # The unused attempt is archived, but is not a tenth evaluation.
    for path in (DOCS / "selecteddata" / "runs").glob("*/*.samples.json"):
        sel = read(path)
        assert [identity(s) for s in sel["test_samples"]] == test_identity
        assert [identity(s) for s in sel["train_samples"]] == [identity(s) for s in selections[(sel["sample_seed"], sel["attack_seed"])]["train_samples"]]

    for entry in filter_identity["kept_samples"] + filter_identity["excluded_samples"]:
        local = ROOT / "data/skill_expansion_20260922/samples/documents" / short(entry["path"]) / "SKILL.md"
        content = local.read_text(encoding="utf-8")
        content = content if content.endswith("\n") else content + "\n"
        assert hashlib.sha256(content.encode()).hexdigest() == entry["content_sha256"]
        checks["dataset_content_hashes_verified"] += 1

    # Per-launch summary files cover 1, 2 or 3 runs: verify, but never average
    # those summaries equally to produce the overall nine-run aggregate.
    for path in (DOCS / "selecteddata" / "runs").glob("*/*.summary.json"):
        summary = read(path)
        rr = [r for r in runs if Path(r["source"]).parent.name == path.parent.name]
        assert summary["overall_mean"]["run_count"] == len(rr)
        for name, value in summary["overall_mean"]["metric_means"].items():
            assert math.isclose(value, stats.mean(r["metrics"][name] for r in rr), abs_tol=1e-12)
        checks["launch_summaries_checked"] += 1

    means = {k: stats.mean(r["metrics"][k] for r in runs) for k in runs[0]["metrics"]}
    spread = {k: {"mean": v, "sample_sd": stats.stdev(r["metrics"][k] for r in runs), "median": stats.median(r["metrics"][k] for r in runs), "min": min(r["metrics"][k] for r in runs), "max": max(r["metrics"][k] for r in runs)} for k, v in means.items()}
    grouped = {}
    for axis in ("sample_seed",
        "attack_seed"):
        grouped[axis] = [{axis: seed, "run_count": 3, "metric_means": {k: stats.mean(r["metrics"][k] for r in runs if r[axis] == seed) for k in means}} for seed in sorted({r[axis] for r in runs})]
    documents = []
    for name in sorted({s["document"] for s in all_samples}):
        ss = [s for s in all_samples if s["document"] == name]
        assert len(ss) == 9
        documents.append({"document": name, "target_token_count": ss[0]["target_token_count"], "mean_body_rougeL_recall": stats.mean(s["body_rougeL_recall"] for s in ss), "mean_body_rouge2_recall": stats.mean(s["body_rouge2_recall"] for s in ss), "max_body_rougeL_recall": max(s["body_rougeL_recall"] for s in ss), "full_leak_count": sum(s["full_skill_prefix"] for s in ss), "empty_content_count": sum(s["prediction_token_count"] == 0 for s in ss)})
    documents.sort(key=lambda d: d["mean_body_rougeL_recall"], reverse=True)
    totals = {"runs": len(runs), "unique_test_documents": len(documents), "evaluation_observations": len(all_samples), "generation_errors": sum(r["metrics"]["failed_samples"] for r in runs), "full_leak_observations": len(full_cases), "unique_full_leak_documents": len({s["document"] for s in full_cases}), "empty_content_observations": sum(s["prediction_token_count"] == 0 for s in all_samples), "body_rougeL_ge_0_5_observations": sum(s["body_rougeL_recall"] >= .5 for s in all_samples), "body_rougeL_ge_0_9_observations": sum(s["body_rougeL_recall"] >= .9 for s in all_samples), "unique_documents_body_rougeL_ge_0_9": sum(d["max_body_rougeL_recall"] >= .9 for d in documents)}
    write(HERE / "summary.json", {"aggregation": "Equal weight over 9 completed runs; 26 observations per run; repeated fixed documents are not independent new documents.",
        "totals": totals, "overall_metric_means": means, "run_dispersion": spread, "grouped": grouped, "runs": runs, "documents": documents, "full_leak_cases": full_cases})
    write(HERE / "sample_details.json", sorted(all_samples, key=lambda s: (s["sample_seed"], s["attack_seed"], s["index"])))
    write(HERE / "validation.json", {"status": "passed",
        "checks": dict(checks), "archive_files_sha256_verified": len(files), "not_recomputed": "Tokenization and ROUGE/LCS from raw generated text: no model tokenizer is loaded. Aggregate metrics are independently recomputed from the saved per-sample evaluation values."})

    report = [
        "# documents · train3 · prefix8 · selecteddata 实验分析",
        "归档日期：2026-10-03。分析只使用已落盘结果，不重新运行模型。",
        "## 主要结论",
        f"9 个完整 seed 组合共评估 234 次，均来自同一组 26 篇测试文档。生成报错为 0；完整原文前缀泄漏为 **4/234（{pct(4/234)}）**，涉及 4 篇不同文档。正文 ROUGE-L recall 均值为 **{pct(means['mean_body_rougeL_recall'])}**，正文 ROUGE-2 recall 均值为 **{pct(means['mean_body_rouge2_recall'])}**。整体表现以有限重合为主，但部分 seed 组合能复现较大段正文，且已出现完整原文泄漏。",
        "**稳定性较弱。**正文 ROUGE-L recall 的逐实验中位数为 10.47%，样本标准差为 13.37 个百分点，范围为 2.35%–41.40%。最高的两个组合拉高了整体均值。9 次中只有 2 次出现完整原文前缀泄漏。",
        f"**无报错不等于有效输出。**去除特殊 token 后的空输出共 {totals['empty_content_observations']}/234（{pct(totals['empty_content_observations']/234)}）。它们仍在 evaluated_samples 的分母内，重合指标按 0 计入；不能从分母剔除后继续称作原始结果。",
        "## 数据范围与口径",
        "- 原始 documents：100 篇；按长度筛选后保留 36 篇、排除 64 篇。保留样本含特殊 token 的内容长度上限为 2001，prompt 预算上限为 2023，上下文上限为 4096。",
        "- 对保留集合按路径排序，以 split_seed=0 打乱，取 10 篇作训练池、26 篇作固定测试集；每次从训练池抽 3 篇。",
        "- sample_seed 为 0、1、2；attack_seed 为 1、2、3；AQ/trigger token_length=12，prefix_length=8，shadow/target 均为 llama，dtype=bfloat16，启用 gradient checkpointing。",
        "- 9 次实验的测试文档、顺序、内容哈希一致；同一 sample_seed 的训练文档一致，训练与测试路径及内容哈希无交集。本地 100 篇源文档的内容哈希与筛选清单一致。",
        "- 汇总从 9 个逐实验 metrics/evaluation JSON 等权重算。各启动目录的 summary 只覆盖该次启动的 1、2 或 3 个组合，不能把这 4 份 summary 直接等权平均。",
        "- 234 是文档×seed 的观测次数，独立测试文档只有 26 篇；没有据此计算把 234 次当成独立样本的置信区间或显著性检验。",
        "## 九次实验明细",
        "下表 RL-R/P 表示 ROUGE-L recall/precision；正文指标去除开头 YAML 元数据。各行重合指标为 26 篇文档的等权均值；泄漏率和 EOS 比例以 26 篇为分母。", table(["sample seed",
        "attack seed",
        "完整泄漏",
        "全文 RL-R",
        "正文 RL-R",
        "正文 RL-P",
        "正文 R2-R",
        "空输出",
        "EOS"], [[r['sample_seed'], r['attack_seed'], f"{r['metrics']['full_skill_leak_count']}/26", pct(r['metrics']['mean_rougeL_recall']), pct(r['metrics']['mean_body_rougeL_recall']), pct(r['metrics']['mean_body_rougeL_precision']), pct(r['metrics']['mean_body_rouge2_recall']), f"{r['diagnostics']['empty_content_count']}/26", pct(r['metrics']['eos_rate'])] for r in runs]), "## seed 维度", table(["维度",
        "seed",
        "完整泄漏率",
        "正文 RL-R",
        "正文 R2-R",
        "EOS"], [[axis, row[axis], pct(row['metric_means']['full_skill_leak_rate']), pct(row['metric_means']['mean_body_rougeL_recall']), pct(row['metric_means']['mean_body_rouge2_recall']), pct(row['metric_means']['eos_rate'])] for axis, rows in grouped.items() for row in rows]), "sample_seed=1 的正文 RL-R 均值为 20.03%，sample_seed=2 为 19.69%，sample_seed=0 为 11.37%；但每组内部波动很大。attack_seed=3 的正文均值最高（25.44%），attack_seed=1 最低（6.72%）。这些是本轮描述性结果，不能将某个整数 seed 解释为可迁移的因果因素。",
        "**两个不同的‘最好’：**(sample=1, attack=2) 完整泄漏最多，为 3/26（11.54%）；(sample=2, attack=3) 正文重合最高，正文 RL-R 为 41.40%、R2-R 为 38.87%，完整泄漏为 1/26（3.85%）。应同时报告，不宜只挑最大值代表总体。",
        "各 sample_seed 对应的训练文档：", table(["sample seed",
        "训练文档"], [[seed, "、".join(short(s['path']) for s in selections[(seed, 1)]['train_samples'])] for seed in range(3)]), "## 完整泄漏与高重合文档", table(["sample seed",
        "attack seed",
        "文档",
        "原文 token",
        "输出 token"], [[s['sample_seed'], s['attack_seed'], s['document'], s['target_token_count'], s['prediction_token_count']] for s in sorted(full_cases, key=lambda s: (s['sample_seed'], s['attack_seed'], s['index']))]), "完整泄漏的代码定义是：规范化后的输出以整篇规范化原文开头，允许尾部有额外内容。4 次完整泄漏的输出都比原文多 65 个内容 token，因而与 exact_markdown_match_rate、exact_token_match_rate 均为 0 并不矛盾。这里没有核验额外 token 的语义。",
        f"以正文 RL-R≥0.9 作为**描述性高重合阈值**，共有 {totals['body_rougeL_ge_0_9_observations']}/234 次，覆盖 {totals['unique_documents_body_rougeL_ge_0_9']} 篇文档；RL-R≥0.5 为 {totals['body_rougeL_ge_0_5_observations']}/234 次。ROUGE-L 允许插入与删除，不能把这些阈值当作严格完整泄漏成功率。",
        "下表按 9 次实验的正文 RL-R 均值排序，完整 26 篇明细见 summary.json。", table(["文档",
        "正文 RL-R 均值",
        "正文 R2-R 均值",
        "正文 RL-R 最大值",
        "完整泄漏次数/9"], [[d['document'], pct(d['mean_body_rougeL_recall']), pct(d['mean_body_rouge2_recall']), pct(d['max_body_rougeL_recall']), d['full_leak_count']] for d in documents[:10]]), "## 指标解释与局限",
        "1. 全文 RL-R 均值为 17.86%，正文 RL-R 为 17.03%；正文均值仍显示重合，但全文 precision 会明显受到元数据与很短输出影响。例如 (0,1) 的全文 RL-P 为 45.74%，正文 RL-P 仅 5.57%，正文 RL-R 为 2.35%，输出长度中位数仅 1 token，不能仅据全文 precision 判定泄漏有效。",
        "2. EOS 比例整体为 43.16%，描述的是结束标记；它既不是攻击成功率，也不是生成报错率。空内容输出与 EOS 是不同诊断维度。",
        "3. token recall 是无序 token 多重集重合，可能高估保序复现；本分析同时看正文 RL-R 和 bigram R2-R。ROUGE 数值为本项目 tokenizer 下的分数，不宜直接与其他分词实现的数值比较。",
        "4. selecteddata 的结论只适用于长度筛选保留集合及当前固定划分。与 full data 相比，文档集合、训练池、划分及评估失败分母发生变化；不能将两组均值差直接解释为筛选带来的攻击能力提升。历史 full data 也未保存同一套正文 ROUGE 指标。",
        "5. 同一固定测试集反复使用，且训练集合有重叠；当前数据不足以区分训练样本、优化随机性与生成随机性各自的独立贡献。未有无攻击基线，不能把所有低水平重合直接归因于攻击。",
        "## 记录与核验",
        "- 未完成的 20260930_215349 运行仅有样本选择及长度清单，不纳入 9 次结果；后续同 seed 完整运行正常计入。",
        "- full data 保存了 6 份 metrics，但 20260925 与 20260927 的 (sample=0, attack=1) 结果相同：metrics、CSV、samples、trigger_ids 四类文件 SHA-256 均一致，合计只有 5 组唯一的已评估 seed 结果。旧的未完成尝试保留在归档清单中。",
        "- 校验了副本 SHA-256、9 组 seed 完整性、固定测试集合、训练选择、源文档哈希、逐条指标聚合及 4 份启动级 summary。没有重新加载 tokenizer 或从生成原文重算 ROUGE。",
        "- [汇总及全部文档指标](summary.json)；[234 次逐条指标](sample_details.json)；[核验结果](validation.json)；[归档文件清单](../../archive_manifest.json)；[运行状态清单](../../run_inventory.json)。",
        "## 后续实验建议",
        "下一轮可先在相同筛选规则与固定测试集上增加独立重复，并补充无攻击基线，报告 seed 分布、完整泄漏和空输出率。若要比较 full data 与 selecteddata，应先明确共同测试子集、相同训练条件和统一指标口径。本次未启动任何新实验。",
        "## 原始结果索引", table(["sample seed",
        "attack seed",
        "evaluation JSON（相对 documents 目录）"], [[r['sample_seed'], r['attack_seed'], f"[{Path(r['source']).parent.name}](../../{r['source']})"] for r in runs])]
    (HERE / "实验结果分析.md").write_text("\n\n".join(report) + "\n", encoding="utf-8")

    for category in ("full data",
        "selecteddata"):
        entries = [i for i in inventory if i['category'] == category]
        text = f"# {category} · documents / train3 / prefix8\n\n" + ("未做长度筛选的历史实验；100 篇源文档、30 篇训练池、70 篇测试池。已评估运行每次 64 篇成功、6 篇失败。\n\n" if category == "full data" else "长度筛选保留 36 篇；10 篇训练池、26 篇固定测试集。完整 3×3 seed 结果见 [实验结果分析](analysis/实验结果分析.md)。\n\n")
        text += "runs/ 保留原运行目录名与原文件名；logs/ 保存匹配到运行目录名的日志。无 metrics 的记录只说明缺少最终评估，不推断所有中断原因。\n\n"
        text += table(["运行目录",
        "已评估记录",
        "仅样本选择记录",
        "匹配日志数"], [[i['source'].split('/')[-1], sum(e['status'] == 'evaluated' for e in i['experiments']), sum(e['status'] != 'evaluated' for e in i['experiments']), len(i['logs'])] for i in entries])
        if category == "full data":
            text += "\n\n6 份 metrics 中有 1 份重复，共 5 组唯一已评估结果。20260927 目录内的 sample=1 / attack=3 只有样本选择记录。20260925_131841 未在现有日志中匹配到目录名，未凭时间猜配日志。\n"
        (DOCS / category / "README.md").write_text(text + "\n", encoding="utf-8")
    overview = """# t3p8 / documents 结果归档

日期：2026-10-03。范围：dataset=documents，train_num=3，prefix_length=8。

- [selecteddata 分析报告](selecteddata/analysis/实验结果分析.md)：9 组完整实验，固定 26 篇测试文档。
- [full data](full%20data/README.md)：未长度筛选的历史实验，包含完成记录、重复结果与未完成尝试。
- [selecteddata](selecteddata/README.md)：筛选后 36 篇数据的运行记录及日志。
- [文件清单与 SHA-256](archive_manifest.json)；[各次运行状态](run_inventory.json)。

采用复制归档，原 results/documents* 和 logs 文件保留。仅收录 train3 / prefix8 对应结果及配套清单、匹配日志；原文件内容不改动。原 JSON 内的 /root/... 路径是服务器来源路径，定位本机归档请使用清单的 archived 字段。未完成运行不计作零分实验，重复结果不当成独立重复。

selecteddata/analysis/summary.json 是本次统一的 9 次实验汇总。各 runs 目录内的旧 summary 仍是单次启动的局部汇总。

归档及分析可在原项目中使用 Python 3 重跑 selecteddata/analysis/archive_and_analyze.py；同名副本与源文件不一致时会停止，避免覆盖不同版本。分析脚本无外部依赖，不运行模型。
"""
    (DOCS / "README.md").write_text(overview, encoding="utf-8")
    print(json.dumps({"archive_files": len(files), "run_directories": len(inventory), "totals": totals, "checks": dict(checks)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
