import argparse
import csv
import gc
import json
import math
import random
from datetime import datetime
from pathlib import Path
from tempfile import mkdtemp


SAMPLE_SEEDS = [0, 1, 2]
ATTACK_SEEDS = [1, 2, 3]
TRAIN_NUMS = [3, 4, 5]
PREFIX_LENGTHS = [8, 16, 32]

# Repeated generation OOMs in the documents runs; filter only after splitting.
KNOWN_OOM_TEST_SKILLS = {
    "documents": {
        "016_clause", "026_docs-cleaner", "091_translate-book",
        "090_technical-documentation", "078_research-report", "028_document-processing",
    },
}

# Backward OOM on the full skill; exclude after splitting, before sampling.
KNOWN_OOM_TRAIN_SKILLS = {
    "documents": {"009_baoyu-slide-deck"},
}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run independent training-sample and attack seeds within one skill dataset."
    )
    parser.add_argument("dataset", help="English skill category name (for example, documents)")
    parser.add_argument("token_length", type=int)
    parser.add_argument("shadow_model")
    parser.add_argument("target_model")
    parser.add_argument(
        "--length-filter", action=argparse.BooleanOptionalAction, default=False,
        help="Enable startup length filtering; disabled by default (known OOM exclusions still apply)",
    )
    parser.add_argument(
        "--trigger-token-reserve", type=int, default=None,
        help="Startup filter's target-tokenizer trigger budget; defaults to token_length "
             "for the same model, required for different shadow/target models",
    )
    parser.add_argument(
        "train_nums", type=int, nargs="*", default=TRAIN_NUMS,
        help="Training sizes; default: TRAIN_NUMS configured in main.py",
    )
    parser.add_argument(
        "--test-num", type=int, default=None,
        help="Fixed test sample count; default: the complete test pool",
    )
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument("--include-known-oom", action="store_true",
                        help="Include the six documents test skills skipped by default after repeated generation OOMs")
    parser.add_argument("--dtype", choices=("float16", "bfloat16"), default="bfloat16",
                        help="Model and 4-bit compute dtype for both attack and evaluation")
    parser.add_argument("--gradient-checkpointing", action=argparse.BooleanOptionalAction, default=True,
                        help="Checkpoint attack forward/backward; candidate evaluation stays in eval mode")
    parser.add_argument("--prefix-lengths", type=int, nargs="+", default=None)
    parser.add_argument("--sample-seeds", type=int, nargs="+", default=None)
    parser.add_argument("--attack-seeds", type=int, nargs="+", default=None)
    args = parser.parse_args(argv)
    if args.token_length <= 0:
        parser.error("token_length must be positive")
    if (args.length_filter and args.trigger_token_reserve is not None
            and args.trigger_token_reserve <= 0):
        parser.error("--trigger-token-reserve must be positive")
    if (args.length_filter and args.shadow_model != args.target_model
            and args.trigger_token_reserve is None):
        parser.error("Different shadow/target models require --trigger-token-reserve "
                     "expressed in target tokenizer tokens")
    if (args.length_filter and args.shadow_model == args.target_model
            and args.trigger_token_reserve is not None
            and args.trigger_token_reserve < args.token_length):
        parser.error("--trigger-token-reserve must be at least token_length for the same model")
    if any(num <= 0 for num in args.train_nums):
        parser.error("train_nums must all be positive")
    if len(set(args.train_nums)) != len(args.train_nums):
        parser.error("train_nums must not contain duplicates")
    if args.test_num is not None and args.test_num <= 0:
        parser.error("--test-num must be positive")
    for field in ("prefix_lengths", "sample_seeds", "attack_seeds"):
        values = getattr(args, field)
        if values is not None:
            if len(set(values)) != len(values):
                parser.error(f"--{field.replace('_', '-')} must not contain duplicates")
            if field == "prefix_lengths" and any(value <= 0 for value in values):
                parser.error("--prefix-lengths must be positive")
            if field != "prefix_lengths" and any(not 0 <= value < 2**32 for value in values):
                parser.error(f"--{field.replace('_', '-')} values must be in [0, 2**32)")
    return args


def execution_config(args):
    return {
        "model_dtype": getattr(args, "dtype", None),
        "gradient_checkpointing": getattr(args, "gradient_checkpointing", False),
    }


def experiment_metadata(args, train_num, test_num, repeat_id, sample_seed,
                        attack_seed, prefix_length, test_selection):
    return {
        "dataset": args.dataset,
        "train_num": train_num,
        "test_num": test_num,
        "repeat_id": repeat_id,
        "sample_seed": sample_seed,
        "attack_seed": attack_seed,
        "token_length": args.token_length,
        "shadow_model": args.shadow_model,
        "target_model": args.target_model,
        "prefix_length": prefix_length,
        "test_selection": test_selection,
        **execution_config(args),
    }


def save_json(path, data, *, allow_nan=True, indent=2, newline=True):
    """Create a JSON artifact without overwriting an existing experiment."""
    with path.open("x", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=indent, allow_nan=allow_nan)
        if newline:
            file.write("\n")


def release_memory(*, collect_ipc=False):
    """Call after deleting model owners so their memory can be reclaimed."""
    import torch

    gc.collect()
    torch.cuda.empty_cache()
    if collect_ipc and torch.cuda.is_available():
        torch.cuda.ipc_collect()


def filter_known_oom_train_samples(train_pool, dataset):
    """Keep split membership and original pool indices; filter before sampling."""
    if not train_pool.train:
        raise ValueError("Training OOM exclusions apply only to the train pool")
    blocked = KNOWN_OOM_TRAIN_SKILLS.get(dataset, set())
    original_count = len(train_pool)
    kept, excluded = [], []
    for index, metadata in enumerate(train_pool.sample_metadata):
        if Path(metadata["path"]).parent.name in blocked:
            excluded.append({**metadata, "reason": "training_backward_cuda_oom"})
        else:
            kept.append(index)
    if not kept:
        raise ValueError("No training samples remain after known OOM exclusions")
    train_pool.dataset = [train_pool.dataset[index] for index in kept]
    train_pool.sample_metadata = [train_pool.sample_metadata[index] for index in kept]
    train_pool.pool_size = len(train_pool)
    print(f"Train pool selection: {original_count} candidates, {len(excluded)} excluded, "
          f"{len(train_pool)} available", flush=True)
    for sample in excluded:
        print(f"Skipping known training OOM: {sample['path']} "
              f"(original pool_index={sample['pool_index']})", flush=True)
    return {
        "exclusion_policy": "known_documents_training_oom_v1" if blocked else "none",
        "train_pool_size_before_exclusion": original_count,
        "train_pool_size_after_exclusion": len(train_pool),
        "excluded_train_num": len(excluded),
        "excluded_train_samples": excluded,
    }


def filter_known_oom_test_samples(testset, dataset, *, include=False):
    """Preserve the original split, selected prefix, order and pool indices."""
    if testset.train:
        raise ValueError("Known OOM exclusions apply only to the test set")
    blocked = set() if include else KNOWN_OOM_TEST_SKILLS.get(dataset, set())
    original_count = len(testset)
    kept, excluded = [], []
    for index, metadata in enumerate(testset.sample_metadata):
        if Path(metadata["path"]).parent.name in blocked:
            excluded.append({**metadata, "reason": "repeated_generation_cuda_oom"})
        else:
            kept.append(index)
    if not kept:
        raise ValueError("No test samples remain after known OOM exclusions")
    testset.dataset = [testset.dataset[index] for index in kept]
    testset.sample_metadata = [testset.sample_metadata[index] for index in kept]
    selection = {
        "exclusion_policy": "known_documents_oom_v1" if blocked else "none",
        "test_num_before_exclusion": original_count,
        "excluded_test_num": len(excluded),
        "excluded_test_samples": excluded,
    }
    print(f"Test selection: {original_count} selected, {len(excluded)} excluded, "
          f"{len(testset)} to evaluate", flush=True)
    for sample in excluded:
        print(f"Skipping known generation OOM: {sample['path']} "
              f"(original pool_index={sample['pool_index']})", flush=True)
    return selection


def save_selection(path, args, train_pool, trainset, testset, repeat_id, sample_seed,
                   attack_seed, prefix_length, test_selection):
    metadata = {
        **experiment_metadata(
            args, len(trainset), len(testset), repeat_id, sample_seed,
            attack_seed, prefix_length, test_selection,
        ),
        "split_seed": 0,
        "train_fraction": 0.3,
        "train_pool_size": len(train_pool),
        "train_samples": trainset.sample_metadata,
        "test_samples": testset.sample_metadata,
    }
    # Save before model loading/training so failed experiments are traceable too.
    save_json(path, metadata)

    print(f"Dataset: {args.dataset}\nTrain num: {len(trainset)}")
    print(f"Repeat: {repeat_id}\nSample seed: {sample_seed}\nAttack seed: {attack_seed}")
    print(f"Execution configuration: {execution_config(args)}")
    for label, samples in (("Train", trainset), ("Test", testset)):
        print(f"\n{label} samples:")
        for number, sample in enumerate(samples.sample_metadata, start=1):
            if label == "Test":
                number = sample["pool_index"] + 1
            print(f"{number}. {sample['path']} (pool_index={sample['pool_index']})")
    print(f"\nSelection saved to: {path}", flush=True)


def save_group_summary(path, runs, sample_seeds, attack_seeds):
    """Average each evaluation metric across either seed axis and both axes."""
    expected = {(sample, attack) for sample in sample_seeds for attack in attack_seeds}
    actual = {(run["sample_seed"], run["attack_seed"]) for run in runs}
    if not runs or actual != expected or len(runs) != len(expected):
        raise ValueError("Cannot summarize an incomplete or duplicate seed grid")
    metric_names = list(runs[0]["metrics"])
    configurations = {(run.get("model_dtype"), run.get("gradient_checkpointing", False)) for run in runs}
    if len(configurations) != 1:
        raise ValueError("Cannot summarize runs with different precision/checkpoint configurations")
    if len({json.dumps(run.get("test_selection"), sort_keys=True) for run in runs}) != 1:
        raise ValueError("Cannot summarize runs with different test exclusions")
    for run in runs:
        if set(run["metrics"]) != set(metric_names):
            raise ValueError("Evaluation metrics differ between experiments")
        if any(not isinstance(value, (int, float)) or not math.isfinite(value)
               for value in run["metrics"].values()):
            raise ValueError("Evaluation metrics must be finite numbers")

    def average(selected):
        return {
            "run_count": len(selected),
            "metric_means": {
                name: math.fsum(run["metrics"][name] for run in selected) / len(selected)
                for name in metric_names
            },
        }

    summary = {
        key: runs[0][key] for key in (
            "dataset", "train_num", "prefix_length", "test_num",
            "token_length", "shadow_model", "target_model",
        )
    }
    summary.update({
        "model_dtype": runs[0].get("model_dtype"),
        "gradient_checkpointing": runs[0].get("gradient_checkpointing", False),
        "test_selection": runs[0].get("test_selection"),
        "sample_seeds": list(sample_seeds),
        "attack_seeds": list(attack_seeds),
        "averaging": "Equal weight per experiment; evaluator values unchanged, including zero-evaluated runs.",
        "zero_evaluated_runs": sum(run["metrics"]["evaluated_samples"] == 0 for run in runs),
        "mean_over_sample_seeds": [
            {"attack_seed": seed, **average([r for r in runs if r["attack_seed"] == seed])}
            for seed in attack_seeds
        ],
        "mean_over_attack_seeds": [
            {"sample_seed": seed, **average([r for r in runs if r["sample_seed"] == seed])}
            for seed in sample_seeds
        ],
        "overall_mean": average(runs),
    })
    save_json(path, summary, allow_nan=False)
    with path.with_suffix(".csv").open("x", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=[
            "average_over", "sample_seed", "attack_seed", "run_count", *metric_names,
        ])
        writer.writeheader()
        for axis, records in (
            ("sample_seed", summary["mean_over_sample_seeds"]),
            ("attack_seed", summary["mean_over_attack_seeds"]),
            ("both", [summary["overall_mean"]]),
        ):
            for record in records:
                writer.writerow({"average_over": axis,
                                 **{k: v for k, v in record.items() if k != "metric_means"},
                                 **record["metric_means"]})
    print("\nParameter group summary:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Summary saved to: {path} and {path.with_suffix('.csv')}", flush=True)


def main(argv=None):
    args = parse_args(argv)
    prefix_lengths = PREFIX_LENGTHS if args.prefix_lengths is None else args.prefix_lengths
    sample_seeds = SAMPLE_SEEDS if args.sample_seeds is None else args.sample_seeds
    attack_seeds = ATTACK_SEEDS if args.attack_seeds is None else args.attack_seeds
    from DataFactory import DataFactory
    from filter_samples import filter_skill_files, save_filter_manifest
    from util.template import TextTemplate

    dataFactory = DataFactory()
    files = dataFactory.get_files(args.dataset)
    tokenizer = None
    context_limit = None
    if args.length_filter:
        from ModelFactory import ModelFactory
        modelFactory = ModelFactory()
        tokenizer = modelFactory.get_tokenizer(args.target_model)
        context_limit = modelFactory.get_context_limit(args.target_model)
    eligible_files, length_filter = filter_skill_files(
        files, tokenizer,
        context_limit=context_limit,
        trigger_token_reserve=(args.token_length if args.trigger_token_reserve is None
                               else args.trigger_token_reserve),
        template=TextTemplate(prefix_1="", prefix_2=""),
        enabled=args.length_filter,
    )
    del tokenizer
    length_filter.update({
        "dataset": args.dataset,
        "shadow_model": args.shadow_model,
        "target_model": args.target_model,
        "trigger_token_length": args.token_length,
        "split_seed": 0,
        "train_fraction": 0.3,
    })
    args.results_dir.mkdir(parents=True, exist_ok=True)
    train_sizes = "-".join(str(num) for num in args.train_nums)
    run_dir = Path(mkdtemp(
        prefix=f"{args.dataset}_train{train_sizes}_{datetime.now():%Y%m%d_%H%M%S}_",
        dir=args.results_dir,
    ))
    manifest_path = run_dir / "length_filter.json"
    # Save even when filtering leaves insufficient data for the requested run.
    save_filter_manifest(manifest_path, length_filter)
    print(f"Results directory: {run_dir}", flush=True)
    print(f"Length filter ({'enabled' if args.length_filter else 'disabled'}): "
          f"{length_filter['source_count']} candidates, "
          f"{length_filter['excluded_count']} excluded, "
          f"{length_filter['kept_count']} kept; manifest: {manifest_path}", flush=True)

    # Split the selected candidates, identically for every experiment.
    train_pool = dataFactory.get_dataset(args.dataset, train=True, num=None,
                                        files=eligible_files)
    testset = dataFactory.get_dataset(args.dataset, train=False, num=args.test_num,
                                     files=eligible_files)
    dataFactory.validate_split(train_pool, testset)
    train_selection = filter_known_oom_train_samples(train_pool, args.dataset)
    test_selection = filter_known_oom_test_samples(
        testset, args.dataset, include=args.include_known_oom,
    )
    test_selection["train_pool_selection"] = train_selection
    test_selection["length_filter"] = {
        key: value for key, value in length_filter.items()
        if key not in ("kept_samples", "excluded_samples")
    }
    test_selection["length_filter"]["manifest_path"] = str(manifest_path.resolve())
    for train_num in args.train_nums:
        if train_num > len(train_pool):
            raise ValueError(
                f"train_num={train_num} exceeds the {len(train_pool)} samples "
                f"in the {args.dataset} train pool"
            )

    import numpy as np
    import torch
    from Attack import HotFlip
    from Sampler import Sampler
    model_options = {"compute_dtype": getattr(torch, args.dtype)}
    attack_options = dict(model_options)
    attack_options["gradient_checkpointing"] = args.gradient_checkpointing

    for train_num in args.train_nums:
        # Sampling depends only on size and seed; reuse it across prefix lengths.
        trainsets = {
            seed: train_pool.sample(num=train_num, seed=seed) for seed in sample_seeds
        }
        for prefix_length in prefix_lengths:
            group_stem = (
                f"{args.dataset}_{args.token_length}_{args.shadow_model}_{args.target_model}"
                f"_train{train_num}_test{len(testset)}_target_prefix{prefix_length}"
                f"_dtype{args.dtype}"
            )
            if args.gradient_checkpointing:
                group_stem += "_gc"
            group_runs = []
            for repeat_id, sample_seed in enumerate(sample_seeds):
                trainset = trainsets[sample_seed]
                for attack_seed in attack_seeds:
                    result_stem = (
                        group_stem
                        + f"_repeat{repeat_id}_sample_seed{sample_seed}_attack_seed{attack_seed}"
                    )
                    save_selection(
                        run_dir / f"{result_stem}.samples.json", args, train_pool,
                        trainset, testset, repeat_id, sample_seed, attack_seed, prefix_length,
                        test_selection,
                    )
                    random.seed(attack_seed)
                    np.random.seed(attack_seed)
                    torch.manual_seed(attack_seed)
                    torch.cuda.manual_seed_all(attack_seed)

                    attack = HotFlip(
                        trigger_token_length=args.token_length,
                        shadow_model=args.shadow_model,
                        template=trainset.template,
                        prefix_length=prefix_length,
                        **attack_options,
                    )
                    attack.replace_triggers(trainset)

                    triggers = attack.decode_triggers()
                    trigger_token_ids = [int(token_id) for token_id in attack.trigger_tokens]
                    trigger_ids_path = run_dir / f"{result_stem}.trigger_ids.json"
                    save_json(trigger_ids_path, trigger_token_ids, indent=None, newline=False)
                    print(f"Trigger token IDs saved to: {trigger_ids_path}")

                    attack.model.zero_grad(set_to_none=True)
                    del attack
                    release_memory(collect_ipc=True)

                    print("GPU memory released; loading target model...")
                    sampler = Sampler(
                        target_model=args.target_model,
                        template=testset.template,
                        **model_options,
                    )
                    results = sampler.sample_sequence(
                        testset,
                        triggers=triggers,
                        trigger_token_ids=(
                            trigger_token_ids
                            if args.shadow_model == args.target_model
                            else None
                        ),
                    )
                    Sampler.save_to_csv(str(run_dir / f"{result_stem}.csv"), results, triggers)
                    report = sampler.evaluate_skill_leakage(results)
                    run_metrics = {
                        **experiment_metadata(
                            args, train_num, len(testset), repeat_id, sample_seed,
                            attack_seed, prefix_length, test_selection,
                        ),
                        "metrics": {key: value for key, value in report.items() if key != "samples"},
                    }
                    save_json(run_dir / f"{result_stem}.metrics.json", run_metrics, allow_nan=False)
                    save_json(
                        run_dir / f"{result_stem}.evaluation.json",
                        {**run_metrics, "samples": report["samples"]},
                        allow_nan=False,
                    )
                    group_runs.append(run_metrics)

                    del sampler
                    release_memory()

            save_group_summary(
                run_dir / f"{group_stem}.summary.json", group_runs, sample_seeds, attack_seeds,
            )


if __name__ == "__main__":
    main()
