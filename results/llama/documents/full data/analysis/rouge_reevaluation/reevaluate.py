"""Re-evaluate saved generations without loading or running an LLM.

Use the project's actual Sampler evaluation methods, extracted with AST to avoid
importing its GPU/model dependencies. Original experiment files stay unchanged.
The public tokenizer must reproduce all available newer full-data evaluations
and all legacy metrics before any of the five new reports is published.
"""
import argparse
import ast
from collections import Counter
import contextlib
import csv
from datetime import datetime
import functools
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import statistics
import sys

HERE = Path(__file__).resolve().parent
FULL = HERE.parents[1]
ROOT = HERE.parents[5]
TOKENIZER_URL = "https://huggingface.co/hf-internal-testing/llama-tokenizer/resolve/main/tokenizer.json"
TOKENIZER_DOWNLOAD_URL = "https://hf-mirror.com/hf-internal-testing/llama-tokenizer/resolve/main/tokenizer.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def exact(a, b, label):
    if isinstance(a, dict) and isinstance(b, dict):
        assert a.keys() == b.keys(), (label, a.keys() ^ b.keys())
        for k in a:
            exact(a[k], b[k], f"{label}.{k}")
    elif isinstance(a, list) and isinstance(b, list):
        assert len(a) == len(b), label
        for i, (left, right) in enumerate(zip(a, b)):
            exact(left, right, f"{label}[{i}]")
    elif isinstance(a, float) or isinstance(b, float):
        assert math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12), (label, a, b)
    else:
        assert a == b, (label, a, b)


def load_results(run):
    selection = read(run / "samples.json")
    with (run / "results.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == len(selection["test_samples"])
    for row, sample in zip(rows, selection["test_samples"]):
        assert hashlib.sha256(row["context"].encode()).hexdigest() == sample["content_sha256"]
        if row.get("sample_path"):
            assert row["sample_path"] == sample["path"]
            assert int(row["sample_index"]) == sample["pool_index"]
        row["sample_path"] = sample["path"]
        row["sample_index"] = sample["pool_index"]
        # CSV booleans must be parsed; bool("False") would be incorrect.
        assert row["ended_with_eos"] in ("True", "False")
        row["ended_with_eos"] = row["ended_with_eos"] == "True"
        row["raw_generation_ids"] = ast.literal_eval(row["raw_generation_ids"])
    return rows


def evaluator(tokenizer_path):
    from tokenizers import Tokenizer
    config = read(tokenizer_path)
    special_ids = [t["id"] for t in config["added_tokens"] if t.get("special")]
    assert set(special_ids) == {0, 1, 2}, special_ids
    backend = Tokenizer.from_file(str(tokenizer_path))

    class Adapter:
        all_special_ids = special_ids

        @functools.lru_cache(maxsize=2500)
        def encode(self, text, add_special_tokens=False):
            return backend.encode(text, add_special_tokens=add_special_tokens).ids

    source_path = ROOT / "Sampler.py"
    tree = ast.parse(source_path.read_text())
    sampler = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Sampler")
    methods = {"normalize_markdown", "content_token_ids", "longest_common_prefix_length", "evaluate_skill_leakage"}
    selected = [n for n in sampler.body if isinstance(n, ast.FunctionDef) and n.name in methods]
    assert len(selected) == len(methods)
    shell = ast.ClassDef(name="OfflineEvaluator", bases=[], keywords=[], body=selected, decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[shell], type_ignores=[]))
    overlap_path = ROOT / "util/overlap_metrics.py"
    spec = importlib.util.spec_from_file_location("experiment_overlap_metrics", overlap_path)
    overlap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(overlap)
    namespace = {"Counter": Counter, "json": json, "rouge_overlap": overlap.rouge_overlap, "strip_yaml_front_matter": overlap.strip_yaml_front_matter, "OVERLAP_FIELDS": overlap.OVERLAP_FIELDS}
    exec(compile(module, str(source_path), "exec"), namespace)
    obj = namespace["OfflineEvaluator"]()
    obj.tokenizer = Adapter()
    return obj


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tokenizer", type=Path, default=HERE / "tokenizer/tokenizer.json")
    parser.add_argument("--dependency-dir", type=Path)
    args = parser.parse_args()
    if args.dependency_dir:
        sys.path.insert(0, str(args.dependency_dir))
    import tokenizers
    csv.field_size_limit(100_000_000)
    score = evaluator(args.tokenizer)
    inputs = {str(p.relative_to(ROOT)): digest(p) for p in (FULL / "runs").glob("*/*") if p.is_file()}
    reports, legacy, calibration, checks = {}, [], [], {}
    for run in sorted((FULL / "runs").iterdir()):
        if not (run / "metrics.json").exists():
            continue
        original = read(run / "metrics.json")
        rows = load_results(run)
        with contextlib.redirect_stdout(io.StringIO()):
            result = score.evaluate_skill_leakage(rows)
        metrics = {k: v for k, v in result.items() if k != "samples"}
        for k, old_value in original["metrics"].items():
            exact(metrics[k], old_value, f"{run.name}.metrics.{k}")
        if (run / "evaluation.json").exists():
            old_evaluation = read(run / "evaluation.json")
            exact(result, {**old_evaluation["metrics"], "samples": old_evaluation["samples"]}, run.name)
            calibration.append(run.name)
            checks[run.name] = {"mode": "all_existing_metrics_and_every_sample_field", "evaluated_samples": result["evaluated_samples"], "status": "passed"}
        else:
            legacy.append(run.name)
            checks[run.name] = {"mode": "all_existing_legacy_metrics", "evaluated_samples": result["evaluated_samples"], "status": "passed"}
        reports[run.name] = {**{k: v for k, v in original.items() if k != "metrics"}, "metrics": metrics, "samples": result["samples"]}
        print(json.dumps({"run": run.name, "evaluated": result["evaluated_samples"], "body_rougeL_recall": result["mean_body_rougeL_recall"], "check": "passed"}), flush=True)
    assert legacy == ["s0a1", "s0a2", "s0a3", "s1a1", "s1a2"]
    assert calibration == ["s1a3", "s2a1", "s2a2", "s2a3"]
    assert sum(reports[k]["metrics"]["evaluated_samples"] for k in calibration) == 201
    assert all(digest(ROOT / p) == h for p, h in inputs.items())
    provenance = {"timestamp": datetime.now().isoformat(timespec="seconds"), "generation_rerun": False, "tokenizer_source": TOKENIZER_URL, "tokenizer_sha256": digest(args.tokenizer), "tokenizers_version": tokenizers.__version__, "tokenizer_note": "Public Llama tokenizer copy; the original server tokenizer file was unavailable. Validated against all saved per-sample fields of four newer full-data runs and every legacy aggregate metric; this establishes agreement on these saved experiments, not byte identity with the server tokenizer.", "sampler_source_sha256": digest(ROOT / "Sampler.py"), "overlap_source_sha256": digest(ROOT / "util/overlap_metrics.py"), "legacy_runs": legacy, "calibration_runs": calibration, "calibration_observations": 201, "legacy_observations": 320, "tolerance": 1e-12, "checks": checks, "source_files_sha256": inputs}
    provenance["tokenizer_download_url"] = TOKENIZER_DOWNLOAD_URL
    for run_id in legacy:
        d = reports[run_id]
        save(HERE / "runs" / run_id / "evaluation.json", {**d, "reevaluation": provenance})
        save(HERE / "runs" / run_id / "metrics.json", {k: v for k, v in d.items() if k != "samples"})
    save(HERE / "validation.json", provenance)
    all_metrics = list(next(iter(reports.values()))["metrics"])
    summary = {"overall_mean": {k: statistics.mean(d["metrics"][k] for d in reports.values()) for k in all_metrics}, "by_sample_seed": {}, "by_attack_seed": {}, "runs": reports}
    for axis in ("sample_seed", "attack_seed"):
        for seed in sorted({d[axis] for d in reports.values()}):
            subset = [d for d in reports.values() if d[axis] == seed]
            summary["by_" + axis][str(seed)] = {k: statistics.mean(d["metrics"][k] for d in subset) for k in all_metrics}
    save(HERE / "all_nine_summary.json", summary)
    rouge = ["mean_rougeL_recall", "mean_rougeL_precision", "mean_rouge2_recall", "mean_body_rougeL_recall", "mean_body_rougeL_precision", "mean_body_rouge2_recall"]
    with (HERE / "前五组_ROUGE补评.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["run_id", "sample_seed", "attack_seed", "total_samples", "evaluated_samples", "failed_samples", *rouge])
        writer.writeheader()
        for run_id in legacy:
            d = reports[run_id]
            writer.writerow({"run_id": run_id, "sample_seed": d["sample_seed"], "attack_seed": d["attack_seed"], **{k: d["metrics"][k] for k in ["total_samples", "evaluated_samples", "failed_samples", *rouge]}})
    lines = ["# 未筛选 t3p8 前五组 ROUGE 补评", "只对已保存的 context / generation 重新评分，没有重新训练或生成。5 次各 70 条原始记录，排除每次 6 条生成失败后，共评分 320 次。", "| seed 组合 | 全文 RL recall | 全文 RL precision | 全文 R2 recall | 正文 RL recall | 正文 RL precision | 正文 R2 recall |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for run_id in legacy:
        lines.append("| " + run_id + " | " + " | ".join(f"{reports[run_id]['metrics'][k]*100:.2f}%" for k in rouge) + " |")
    lines += ["", "评分直接复用当前 Sampler.py 的 normalize_markdown、content_token_ids 与 evaluate_skill_leakage，使用 util/overlap_metrics.py 的 ROUGE 实现。空输出保留为零分；失败生成不进入该次重合指标均值。正文指标按项目规则去除开头 YAML 元数据。", "", "使用 [Hugging Face 公开 Llama tokenizer](https://huggingface.co/hf-internal-testing/llama-tokenizer/blob/main/tokenizer.json)。原服务器 tokenizer 文件未取得，因此先用新四组 201 条逐样本记录校验：全部已有指标与 token 数均一致（浮点容差 1e-12）；旧五组全部已有指标也一致。记录了 tokenizer 与代码 SHA-256，未声称公开文件与服务器文件字节相同。", "", "原始 runs 目录文件未修改；补评结果单独存于本目录 runs/s*/。validation.json 记录校验依据；all_nine_summary.json 提供整合新旧九组后的指标与分组均值。"]
    (HERE / "补评说明.md").write_text("\n\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "legacy_runs_reevaluated": len(legacy), "calibration_runs": len(calibration), "overall": summary["overall_mean"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
