import argparse
import csv
import gc
import json
import math
import random
from datetime import datetime
from pathlib import Path
from tempfile import mkdtemp


SAMPLE_SEEDS = [0, 1, 2, 3, 4]
ATTACK_SEEDS = [ 1, 2, 3, 4, 5]
TRAIN_NUMS = [ 3, 4,5,6]
PREFIX_LENGTHS = [8,16,32]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run independent training-sample and attack seeds within one skill dataset."
    )
    parser.add_argument("dataset", help="English skill category name (for example, documents)")
    parser.add_argument("token_length", type=int)
    parser.add_argument("shadow_model")
    parser.add_argument("target_model")
    parser.add_argument(
        "train_nums", type=int, nargs="*", default=TRAIN_NUMS,
        help="Training sizes; default: TRAIN_NUMS configured in main.py",
    )
    parser.add_argument(
        "--test-num", type=int, default=None,
        help="Fixed test sample count; default: the complete test pool",
    )
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    args = parser.parse_args(argv)
    if any(num <= 0 for num in args.train_nums):
        parser.error("train_nums must all be positive")
    if len(set(args.train_nums)) != len(args.train_nums):
        parser.error("train_nums must not contain duplicates")
    if args.test_num is not None and args.test_num <= 0:
        parser.error("--test-num must be positive")
    return args


def save_selection(path, args, train_pool, trainset, testset, repeat_id, sample_seed,
                   attack_seed, prefix_length):
    metadata = {
        "dataset": args.dataset,
        "train_num": len(trainset),
        "test_num": len(testset),
        "repeat_id": repeat_id,
        "sample_seed": sample_seed,
        "attack_seed": attack_seed,
        "split_seed": 0,
        "train_fraction": 0.3,
        "train_pool_size": len(train_pool),
        "token_length": args.token_length,
        "shadow_model": args.shadow_model,
        "target_model": args.target_model,
        "prefix_length": prefix_length,
        "train_samples": trainset.sample_metadata,
        "test_samples": testset.sample_metadata,
    }
    # Save before model loading/training so failed experiments are traceable too.
    with path.open("x", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2)
        file.write("\n")

    print(f"Dataset: {args.dataset}\nTrain num: {len(trainset)}")
    print(f"Repeat: {repeat_id}\nSample seed: {sample_seed}\nAttack seed: {attack_seed}")
    for label, samples in (("Train", trainset), ("Test", testset)):
        print(f"\n{label} samples:")
        for number, sample in enumerate(samples.sample_metadata, start=1):
            print(f"{number}. {sample['path']} (pool_index={sample['pool_index']})")
    print(f"\nSelection saved to: {path}", flush=True)


def save_group_summary(path, runs, sample_seeds, attack_seeds):
    """Average each evaluation metric across either seed axis and both axes."""
    expected = {(sample, attack) for sample in sample_seeds for attack in attack_seeds}
    actual = {(run["sample_seed"], run["attack_seed"]) for run in runs}
    if not runs or actual != expected or len(runs) != len(expected):
        raise ValueError("Cannot summarize an incomplete or duplicate seed grid")
    metric_names = list(runs[0]["metrics"])
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
    with path.open("x", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2, allow_nan=False)
        file.write("\n")
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
    from DataFactory import DataFactory

    dataFactory = DataFactory()
    # Both pools come from this dataset's fixed 30/70 partition.
    train_pool = dataFactory.get_dataset(args.dataset, train=True, num=None)
    testset = dataFactory.get_dataset(args.dataset, train=False, num=args.test_num)
    dataFactory.validate_split(train_pool, testset)
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

    args.results_dir.mkdir(parents=True, exist_ok=True)
    # A fresh directory also protects previous runs of the same configuration.
    train_sizes = "-".join(str(num) for num in args.train_nums)
    run_dir = Path(mkdtemp(
        prefix=f"{args.dataset}_train{train_sizes}_{datetime.now():%Y%m%d_%H%M%S}_",
        dir=args.results_dir,
    ))
    print(f"Results directory: {run_dir}", flush=True)

    for train_num in args.train_nums:
        for prefix_length in PREFIX_LENGTHS:
            group_stem = (
                f"{args.dataset}_{args.token_length}_{args.shadow_model}_{args.target_model}"
                f"_train{train_num}_test{len(testset)}_target_prefix{prefix_length}"
            )
            group_runs = []
            for repeat_id, sample_seed in enumerate(SAMPLE_SEEDS):
                trainset = train_pool.sample(num=train_num, seed=sample_seed)
                for attack_seed in ATTACK_SEEDS:
                    result_stem = (
                        group_stem
                        + f"_repeat{repeat_id}_sample_seed{sample_seed}_attack_seed{attack_seed}"
                    )
                    save_selection(
                        run_dir / f"{result_stem}.samples.json", args, train_pool,
                        trainset, testset, repeat_id, sample_seed, attack_seed, prefix_length,
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
                    )
                    attack.replace_triggers(trainset)

                    triggers = attack.decode_triggers()
                    trigger_token_ids = [int(token_id) for token_id in attack.trigger_tokens]
                    trigger_ids_path = run_dir / f"{result_stem}.trigger_ids.json"
                    with trigger_ids_path.open("x", encoding="utf-8") as file:
                        json.dump(trigger_token_ids, file)
                    print(f"Trigger token IDs saved to: {trigger_ids_path}")

                    attack.model.zero_grad(set_to_none=True)
                    del attack
                    gc.collect()
                    torch.cuda.empty_cache()
                    if torch.cuda.is_available():
                        torch.cuda.ipc_collect()

                    print("GPU memory released; loading target model...")
                    sampler = Sampler(
                        target_model=args.target_model,
                        template=testset.template,
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
                        "dataset": args.dataset,
                        "train_num": train_num,
                        "prefix_length": prefix_length,
                        "test_num": len(testset),
                        "token_length": args.token_length,
                        "shadow_model": args.shadow_model,
                        "target_model": args.target_model,
                        "repeat_id": repeat_id,
                        "sample_seed": sample_seed,
                        "attack_seed": attack_seed,
                        "metrics": {key: value for key, value in report.items() if key != "samples"},
                    }
                    with (run_dir / f"{result_stem}.metrics.json").open("x", encoding="utf-8") as file:
                        json.dump(run_metrics, file, ensure_ascii=False, indent=2, allow_nan=False)
                        file.write("\n")
                    group_runs.append(run_metrics)

                    del sampler
                    gc.collect()
                    torch.cuda.empty_cache()

            save_group_summary(
                run_dir / f"{group_stem}.summary.json", group_runs, SAMPLE_SEEDS, ATTACK_SEEDS,
            )


if __name__ == "__main__":
    main()
