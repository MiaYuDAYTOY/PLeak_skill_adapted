"""Exercise repeat orchestration without loading models or third-party packages."""

import builtins
import contextlib
import csv
import importlib.util
import io
import json
from pathlib import Path
import random
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


MAIN_PATH = Path(__file__).resolve().parents[1] / "main.py"
MAIN_SPEC = importlib.util.spec_from_file_location("pleak_main_repeats_test", MAIN_PATH)
MAIN = importlib.util.module_from_spec(MAIN_SPEC)
MAIN_SPEC.loader.exec_module(MAIN)


class DatasetStub:
    def __init__(self, split, indices):
        self.template = "skill-template"
        self.indices = list(indices)
        self.sample_metadata = [
            {
                "path": f"/skills/{split}/skill-{index}/SKILL.md",
                "pool_index": index,
                "content_sha256": f"{split}-{index}",
            }
            for index in self.indices
        ]

    def __len__(self):
        return len(self.indices)


class ExperimentHarness:
    """Record dependencies' observable calls; sampling uses a local Python RNG."""

    def __init__(self, results_dir, pool_size=12):
        self.results_dir = Path(results_dir)
        self.train_pool = DatasetStub("train", range(pool_size))
        self.test_pool = DatasetStub("test", range(5))
        self.dataset_calls = []
        self.split_calls = []
        self.training_calls = []
        self.attack_calls = []
        self.replace_calls = []
        self.sampler_calls = []
        self.sample_calls = []
        self.evaluate_calls = []
        self.csv_calls = []
        self.numpy_seeds = []
        self.torch_seeds = []
        self.cuda_seeds = []
        self.seen_selections = set()
        harness = self

        class DataFactory:
            def get_dataset(self, name, *, train, num):
                if train:
                    dataset = harness.train_pool
                else:
                    indices = harness.test_pool.indices
                    dataset = DatasetStub("test", indices if num is None else indices[:num])
                harness.dataset_calls.append((name, train, num, dataset))
                return dataset

            @staticmethod
            def validate_split(train_pool, testset):
                harness.split_calls.append((train_pool, testset))

        def sample_train_pool(num, seed):
            train_pool = harness.train_pool
            selected = random.Random(seed).sample(train_pool.indices, num)
            dataset = DatasetStub("train", selected)
            harness.training_calls.append((train_pool, num, seed, dataset))
            return dataset

        self.train_pool.sample = sample_train_pool

        class HotFlip:
            def __init__(self, **kwargs):
                self.seed = harness.torch_seeds[-1]
                self.trigger_tokens = [100 + self.seed, 200 + self.seed]
                self.model = types.SimpleNamespace(zero_grad=lambda **unused: None)
                # Snapshot on construction, so later writes cannot satisfy this check.
                paths = set(harness.results_dir.rglob("*.samples.json"))
                new_paths = paths - harness.seen_selections
                harness.seen_selections.update(paths)
                saved_selections = {
                    path: json.loads(path.read_text(encoding="utf-8"))
                    for path in new_paths
                }
                harness.attack_calls.append((self, kwargs, saved_selections))

            def replace_triggers(self, trainset):
                harness.replace_calls.append((self, trainset))

            def decode_triggers(self):
                return f"trigger-seed-{self.seed}"

        class Sampler:
            def __init__(self, **kwargs):
                self.seed = harness.torch_seeds[-1]
                harness.sampler_calls.append((self, kwargs))

            def sample_sequence(self, testset, **kwargs):
                results = [{"seed": self.seed, "test_count": len(testset)}]
                harness.sample_calls.append((self, testset, kwargs, results))
                return results

            @staticmethod
            def save_to_csv(path, results, triggers):
                harness.csv_calls.append((Path(path), results, triggers))
                Path(path).write_text(
                    f"seed,triggers\n{results[0]['seed']},{triggers}\n",
                    encoding="utf-8",
                )

            def evaluate_skill_leakage(self, results):
                harness.evaluate_calls.append((self, results))
                metadata = next(iter(harness.attack_calls[-1][2].values()))
                rate = (10 * metadata["sample_seed"] + self.seed) / 100
                count = results[0]["test_count"]
                return {
                    "total_samples": count, "evaluated_samples": count, "failed_samples": 0,
                    "full_skill_leak_rate": rate,
                    "mean_token_recall": rate / 2,
                    "samples": [{"index": 0}],
                }

        self.modules = {}
        for name in ("DataFactory", "Attack", "Sampler", "numpy", "torch"):
            self.modules[name] = types.ModuleType(name)
        self.modules["DataFactory"].DataFactory = DataFactory
        self.modules["Attack"].HotFlip = HotFlip
        self.modules["Sampler"].Sampler = Sampler
        self.modules["numpy"].random = types.SimpleNamespace(seed=self.numpy_seeds.append)
        self.modules["torch"].manual_seed = self.torch_seeds.append
        self.modules["torch"].cuda = types.SimpleNamespace(
            manual_seed_all=self.cuda_seeds.append,
            empty_cache=lambda: None,
            is_available=lambda: False,
            ipc_collect=lambda: None,
        )

    def run(self, train_num=3, test_num=2, target_model="model", shadow_model="model",
            train_nums=None, extra_args=None):
        sizes = [train_num] if train_nums is None else train_nums
        argv = ["webtesting", "7", shadow_model, target_model] + [str(n) for n in sizes]
        if test_num is not None:
            argv += ["--test-num", str(test_num)]
        argv += ["--results-dir", str(self.results_dir)]
        argv += extra_args or []
        output = io.StringIO()
        random_state = random.getstate()
        try:
            with patch.dict(sys.modules, self.modules), contextlib.redirect_stdout(output):
                with patch.object(MAIN.gc, "collect", return_value=0):
                    MAIN.main(argv)
        finally:
            random.setstate(random_state)
        return output.getvalue()


class MainRepeatsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.results_dir = Path(self.temporary.name) / "results"

    def test_precision_checkpoint_and_single_run_flags_reach_models_and_metadata(self):
        harness = ExperimentHarness(self.results_dir)
        dtype = object()
        harness.modules['torch'].bfloat16 = dtype
        harness.run(extra_args=['--dtype', 'bfloat16', '--gradient-checkpointing',
                                '--prefix-lengths', '8', '--sample-seeds', '0',
                                '--attack-seeds', '1'])
        self.assertEqual(len(harness.attack_calls), 1)
        attack_options = harness.attack_calls[0][1]
        self.assertIs(attack_options['compute_dtype'], dtype)
        self.assertTrue(attack_options['gradient_checkpointing'])
        self.assertEqual(attack_options['prefix_length'], 8)
        self.assertIs(harness.sampler_calls[0][1]['compute_dtype'], dtype)
        self.assertNotIn('gradient_checkpointing', harness.sampler_calls[0][1])
        for pattern in ('*.samples.json', '*.metrics.json', '*.summary.json'):
            files = list(self.results_dir.rglob(pattern))
            self.assertEqual(len(files), 1)
            metadata = json.loads(files[0].read_text())
            self.assertEqual(metadata['model_dtype'], 'bfloat16')
            self.assertTrue(metadata['gradient_checkpointing'])
            self.assertIn('_dtypebfloat16_gc', files[0].name)

    def test_precision_and_seed_options_preserve_defaults_and_validate_overrides(self):
        base = ['documents', '12', 'llama', 'llama', '3']
        defaults = MAIN.parse_args(base)
        self.assertIsNone(defaults.dtype)
        self.assertFalse(defaults.gradient_checkpointing)
        self.assertIsNone(defaults.prefix_lengths)
        for flags in (['--prefix-lengths', '0'], ['--sample-seeds', '-1'],
                      ['--attack-seeds', '1', '1']):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                MAIN.parse_args(base + flags)

    def test_five_sample_seeds_each_run_six_attacks_on_one_fixed_testset(self):
        harness = ExperimentHarness(self.results_dir)
        output = harness.run(train_num=3, test_num=2)
        self.assertEqual(
            [(name, train, num) for name, train, num, _ in harness.dataset_calls],
            [("webtesting", True, None), ("webtesting", False, 2)],
        )
        testset = harness.dataset_calls[1][3]
        self.assertEqual(harness.split_calls, [(harness.train_pool, testset)])
        attack_seeds = list(range(6)) * 5
        self.assertEqual(harness.numpy_seeds, attack_seeds)
        self.assertEqual(harness.torch_seeds, attack_seeds)
        self.assertEqual(harness.cuda_seeds, attack_seeds)
        self.assertEqual(len(harness.training_calls), 5)
        for calls in (harness.attack_calls, harness.replace_calls, harness.sampler_calls,
                      harness.sample_calls, harness.csv_calls, harness.evaluate_calls):
            self.assertEqual(len(calls), 30)
        self.assertEqual(len({id(call[0]) for call in harness.attack_calls}), 30)
        self.assertEqual(len({id(call[0]) for call in harness.sampler_calls}), 30)
        for sample_seed in range(5):
            pool, num, recorded_seed, trainset = harness.training_calls[sample_seed]
            self.assertIs(pool, harness.train_pool)
            self.assertEqual((num, recorded_seed), (3, sample_seed))
            self.assertEqual(trainset.indices, random.Random(sample_seed).sample(range(12), 3))
            self.assertEqual(len(set(trainset.indices)), 3)
            for attack_seed in range(6):
                index = sample_seed * 6 + attack_seed
                attack, attack_kwargs, saved = harness.attack_calls[index]
                self.assertEqual(harness.replace_calls[index], (attack, trainset))
                self.assertEqual(attack_kwargs["template"], trainset.template)
                self.assertEqual(attack_kwargs["trigger_token_length"], 7)
                self.assertEqual(len(saved), 1, "Selection must exist before HotFlip construction")
                path, metadata = next(iter(saved.items()))
                self.assertEqual(metadata["dataset"], "webtesting")
                self.assertEqual(metadata["train_num"], 3)
                self.assertEqual(metadata["train_fraction"], 0.3)
                self.assertEqual(metadata["repeat_id"], sample_seed)
                self.assertEqual(metadata["sample_seed"], sample_seed)
                self.assertEqual(metadata["attack_seed"], attack_seed)
                self.assertNotIn("seed", metadata)
                self.assertEqual(metadata["train_samples"], trainset.sample_metadata)
                self.assertEqual(metadata["test_samples"], testset.sample_metadata)
                self.assertIn(f"_sample_seed{sample_seed}_attack_seed{attack_seed}", path.name)
                sampler, sampler_kwargs = harness.sampler_calls[index]
                sampled_by, sampled_set, sample_kwargs, results = harness.sample_calls[index]
                self.assertIs(sampled_by, sampler)
                self.assertIs(sampled_set, testset)
                self.assertEqual(sampler_kwargs["template"], testset.template)
                self.assertEqual(sample_kwargs["triggers"], f"trigger-seed-{attack_seed}")
                self.assertEqual(sample_kwargs["trigger_token_ids"], [100 + attack_seed, 200 + attack_seed])
                self.assertEqual(harness.evaluate_calls[index], (sampler, results))
                self.assertIs(harness.csv_calls[index][1], results)
                self.assertIn(f"Sample seed: {sample_seed}\nAttack seed: {attack_seed}", output)
        for sample in testset.sample_metadata:
            self.assertEqual(output.count(sample["path"]), 30)

    def test_repeat_outputs_and_reruns_never_overwrite(self):
        harness = ExperimentHarness(self.results_dir)
        harness.run()
        first_dirs = list(self.results_dir.iterdir())
        self.assertEqual(len(first_dirs), 1)
        first_dir = first_dirs[0]
        snapshot = {path: path.read_bytes() for path in first_dir.iterdir()}
        self.assertEqual(len(snapshot), 122)
        for suffix in (".csv", ".trigger_ids.json", ".samples.json", ".metrics.json"):
            paths = [path for path in first_dir.glob(f"*{suffix}")
                     if not path.name.endswith(".summary.csv")]
            self.assertEqual(len(paths), 30)
            for sample_seed in range(5):
                for attack_seed in range(6):
                    matches = [path for path in paths if
                               f"_sample_seed{sample_seed}_attack_seed{attack_seed}." in path.name]
                    self.assertEqual(len(matches), 1)
        for path in first_dir.glob("*.trigger_ids.json"):
            attack_seed = int(path.name.split("_attack_seed")[1].split(".")[0])
            self.assertEqual(json.loads(path.read_text()), [100 + attack_seed, 200 + attack_seed])

        harness.run()
        all_dirs = set(self.results_dir.iterdir())
        self.assertEqual(len(all_dirs), 2)
        second_dir = (all_dirs - {first_dir}).pop()
        self.assertEqual(len(list(second_dir.iterdir())), 122)
        self.assertEqual(snapshot, {path: path.read_bytes() for path in first_dir.iterdir()})
        first_metadata = [
            json.loads(path.read_text()) for path in sorted(first_dir.glob("*.samples.json"))
        ]
        second_metadata = [
            json.loads(path.read_text()) for path in sorted(second_dir.glob("*.samples.json"))
        ]
        self.assertEqual(first_metadata, second_metadata)

    def test_each_parameter_group_has_correct_seed_means_and_raw_metrics(self):
        harness = ExperimentHarness(self.results_dir)
        with patch.object(MAIN, "PREFIX_LENGTHS", [8, 16]):
            output = harness.run(train_nums=[3, 5])
        summaries = list(self.results_dir.rglob("*.summary.json"))
        self.assertEqual(len(summaries), 4)
        self.assertEqual(output.count("Parameter group summary:"), 4)
        self.assertEqual(len(list(self.results_dir.rglob("*.metrics.json"))), 120)
        groups = set()
        for path in summaries:
            summary = json.loads(path.read_text())
            groups.add((summary["train_num"], summary["prefix_length"]))
            for row in summary["mean_over_sample_seeds"]:
                self.assertEqual(row["run_count"], 5)
                self.assertAlmostEqual(row["metric_means"]["full_skill_leak_rate"],
                                       (20 + row["attack_seed"]) / 100)
            for row in summary["mean_over_attack_seeds"]:
                self.assertEqual(row["run_count"], 6)
                self.assertAlmostEqual(row["metric_means"]["full_skill_leak_rate"],
                                       (10 * row["sample_seed"] + 2.5) / 100)
            self.assertEqual(summary["overall_mean"]["run_count"], 30)
            self.assertAlmostEqual(summary["overall_mean"]["metric_means"]["full_skill_leak_rate"], .225)
            self.assertAlmostEqual(summary["overall_mean"]["metric_means"]["mean_token_recall"], .1125)
            self.assertNotIn("samples", summary["overall_mean"]["metric_means"])
            with path.with_suffix(".csv").open(newline="") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 12)
            overall = next(row for row in rows if row["average_over"] == "both")
            self.assertEqual((overall["sample_seed"], overall["attack_seed"]), ("", ""))
            self.assertAlmostEqual(float(overall["full_skill_leak_rate"]), .225)
        self.assertEqual(groups, {(3, 8), (3, 16), (5, 8), (5, 16)})
        for path in self.results_dir.rglob("*.metrics.json"):
            record = json.loads(path.read_text())
            self.assertAlmostEqual(record["metrics"]["full_skill_leak_rate"],
                                   (10 * record["sample_seed"] + record["attack_seed"]) / 100)

    def test_changing_train_num_resamples_without_changing_test_samples(self):
        harness = ExperimentHarness(self.results_dir)
        harness.run(train_num=3)
        harness.run(train_num=5)
        first_testset = harness.dataset_calls[1][3]
        second_testset = harness.dataset_calls[3][3]
        self.assertEqual(first_testset.sample_metadata, second_testset.sample_metadata)
        for offset, size in ((0, 3), (5, 5)):
            for seed in range(5):
                _, num, recorded_seed, selected = harness.training_calls[offset + seed]
                self.assertEqual((num, recorded_seed), (size, seed))
                self.assertEqual(selected.indices, random.Random(seed).sample(range(12), size))

    def test_oversized_train_num_fails_before_importing_models(self):
        harness = ExperimentHarness(self.results_dir, pool_size=2)
        original_import = builtins.__import__
        attempted_model_imports = []

        def tracked_import(name, *args, **kwargs):
            if name in ("Attack", "Sampler", "torch", "numpy"):
                attempted_model_imports.append(name)
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=tracked_import):
            with self.assertRaisesRegex(ValueError, "train_num=3 exceeds.*2 samples"):
                harness.run(train_num=3)
        self.assertEqual(attempted_model_imports, [])
        self.assertEqual(harness.attack_calls, [])
        self.assertEqual(harness.sampler_calls, [])
        self.assertFalse(self.results_dir.exists())

    def test_different_target_model_does_not_reuse_shadow_token_ids(self):
        harness = ExperimentHarness(self.results_dir)
        harness.run(shadow_model="shadow", target_model="target")
        self.assertTrue(all(call[2]["trigger_token_ids"] is None for call in harness.sample_calls))

    def test_cli_retains_fifth_positional_train_num_and_optional_test_num(self):
        args = MAIN.parse_args(["webtesting", "9", "shadow", "target", "3", "--test-num", "4"])
        self.assertEqual(args.dataset, "webtesting")
        self.assertEqual(args.token_length, 9)
        self.assertEqual(args.shadow_model, "shadow")
        self.assertEqual(args.target_model, "target")
        self.assertEqual(args.train_nums, [3])
        self.assertEqual(args.test_num, 4)
        defaults = MAIN.parse_args(["documents", "9", "shadow", "target", "5"])
        self.assertEqual(defaults.train_nums, [5])
        self.assertIsNone(defaults.test_num)
        defaults = MAIN.parse_args(["documents", "9", "shadow", "target"])
        self.assertEqual(defaults.train_nums, MAIN.TRAIN_NUMS)
        multiple = MAIN.parse_args(["documents", "9", "shadow", "target", "1", "3", "5"])
        self.assertEqual(multiple.train_nums, [1, 3, 5])

    def test_train_sizes_and_prefix_lengths_share_testset_and_distinct_outputs(self):
        harness = ExperimentHarness(self.results_dir, pool_size=30)
        with patch.object(MAIN, "PREFIX_LENGTHS", [8, 16]):
            harness.run(train_nums=[1, 3, 5, 8, 16])
        self.assertEqual(len(harness.dataset_calls), 2)
        testset = harness.dataset_calls[1][3]
        self.assertTrue(all(call[1] is testset for call in harness.sample_calls))
        self.assertEqual(len(harness.training_calls), 50)
        self.assertEqual(len(harness.attack_calls), 300)
        self.assertEqual(len(harness.evaluate_calls), 300)
        self.assertEqual(len(list(self.results_dir.rglob("*.csv"))), 310)
        self.assertEqual(len(list(self.results_dir.rglob("*.summary.json"))), 10)
        selections = [next(iter(call[2].values())) for call in harness.attack_calls]
        expected = [(n, prefix, sample_seed, attack_seed)
                    for n in [1, 3, 5, 8, 16] for prefix in [8, 16]
                    for sample_seed in range(5) for attack_seed in range(6)]
        self.assertEqual([(m["train_num"], m["prefix_length"], m["sample_seed"], m["attack_seed"])
                          for m in selections], expected)
        for m in selections:
            self.assertEqual(len(m["train_samples"]), m["train_num"])
            self.assertEqual(m["test_samples"], testset.sample_metadata)

    def test_attack_seed_changes_do_not_change_training_selection(self):
        harness = ExperimentHarness(self.results_dir)
        with patch.object(MAIN, "SAMPLE_SEEDS", [11, 23]):
            with patch.object(MAIN, "ATTACK_SEEDS", [2, 5]):
                harness.run()
            with patch.object(MAIN, "ATTACK_SEEDS", [5, 1, 4]):
                harness.run()
        self.assertEqual([call[2] for call in harness.training_calls], [11, 23, 11, 23])
        self.assertEqual(harness.torch_seeds, [2, 5, 2, 5, 5, 1, 4, 5, 1, 4])
        for index in range(2):
            self.assertEqual(harness.training_calls[index][3].sample_metadata,
                             harness.training_calls[index + 2][3].sample_metadata)
        for index, call in enumerate(harness.attack_calls[:4]):
            metadata = next(iter(call[2].values()))
            self.assertEqual(metadata["repeat_id"], index // 2)
            self.assertEqual(metadata["sample_seed"], [11, 23][index // 2])
            self.assertEqual(metadata["attack_seed"], [2, 5][index % 2])

    def test_invalid_training_size_in_list_fails_before_any_experiment(self):
        harness = ExperimentHarness(self.results_dir, pool_size=12)
        with self.assertRaisesRegex(ValueError, "train_num=16 exceeds"):
            harness.run(train_nums=[3, 16])
        self.assertEqual(harness.attack_calls, [])
        for sizes in ([3, 3], [3, 0], [3, -1]):
            with self.subTest(sizes=sizes), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    MAIN.parse_args(["documents", "9", "shadow", "target"]
                                    + [str(n) for n in sizes])

    def test_summary_keeps_equal_run_weights_and_records_failed_evaluations(self):
        common = dict(dataset="documents", train_num=3, prefix_length=8, test_num=10,
                      token_length=7, shadow_model="model", target_model="model")
        runs = [
            dict(common, sample_seed=11, attack_seed=5, metrics={
                "evaluated_samples": 0, "failed_samples": 10, "full_skill_leak_rate": 0.0,
            }),
            dict(common, sample_seed=23, attack_seed=5, metrics={
                "evaluated_samples": 10, "failed_samples": 0, "full_skill_leak_rate": 1.0,
            }),
        ]
        path = Path(self.temporary.name) / "failed_evaluation.summary.json"
        with contextlib.redirect_stdout(io.StringIO()):
            MAIN.save_group_summary(path, runs, [11, 23], [5])
        summary = json.loads(path.read_text())
        self.assertEqual(summary["zero_evaluated_runs"], 1)
        self.assertEqual(summary["overall_mean"]["metric_means"], {
            "evaluated_samples": 5.0, "failed_samples": 5.0, "full_skill_leak_rate": .5,
        })
        self.assertEqual(summary["mean_over_sample_seeds"][0]["attack_seed"], 5)

    def test_summary_rejects_incomplete_duplicate_and_invalid_metrics(self):
        common = dict(dataset="documents", train_num=3, prefix_length=8, test_num=10,
                      token_length=7, shadow_model="model", target_model="model")
        run = dict(common, sample_seed=0, attack_seed=0,
                   metrics={"evaluated_samples": 10, "full_skill_leak_rate": .5})
        cases = [
            ([], [0], [0]),
            ([run], [0, 1], [0]),
            ([run, run], [0], [0]),
            ([dict(run, metrics={"evaluated_samples": 10,
                                 "full_skill_leak_rate": float("nan")})], [0], [0]),
            ([run, dict(run, sample_seed=1, metrics={"evaluated_samples": 10})], [0, 1], [0]),
        ]
        path = Path(self.temporary.name) / "invalid.summary.json"
        for runs, samples, attacks in cases:
            with self.subTest(runs=runs), self.assertRaises(ValueError):
                MAIN.save_group_summary(path, runs, samples, attacks)
            self.assertFalse(path.exists())

    def test_default_test_num_loads_the_full_test_pool(self):
        harness = ExperimentHarness(self.results_dir)
        harness.run(test_num=None)
        self.assertEqual(harness.dataset_calls[1][2], None)
        testset = harness.dataset_calls[1][3]
        self.assertEqual(len(testset), 5)
        self.assertTrue(all(call[1] is testset for call in harness.sample_calls))


if __name__ == "__main__":
    unittest.main()
