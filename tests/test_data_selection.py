"""Selection regressions; no model downloads or attack execution are required.

Run from the repository root with:
    python3 -m unittest discover -s tests -p 'test_data_selection.py' -v
"""

import copy
import hashlib
import importlib
import importlib.util
import os
from pathlib import Path
import random
import sys
import tempfile
import types
import unittest
from functools import partial
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))


def _import_data_factory():
    """Stub unavailable, unused model dependencies only during module import."""
    stubs = {}
    if importlib.util.find_spec("torch") is None:
        torch = types.ModuleType("torch")
        torch_utils = types.ModuleType("torch.utils")
        torch_data = types.ModuleType("torch.utils.data")

        class Dataset:
            def __iter__(self):
                for index in range(len(self)):
                    yield self[index]

        torch_data.Dataset = Dataset
        torch_utils.data = torch_data
        torch.utils = torch_utils
        stubs.update({"torch": torch, "torch.utils": torch_utils,
                      "torch.utils.data": torch_data})
    if importlib.util.find_spec("datasets") is None:
        datasets = types.ModuleType("datasets")

        def no_network(*args, **kwargs):
            raise AssertionError("Selection tests must not download datasets")

        datasets.load_dataset = no_network
        stubs["datasets"] = datasets
    if importlib.util.find_spec("transformers") is None:
        transformers = types.ModuleType("transformers")
        for name in ("AutoTokenizer", "AutoModelForCausalLM", "BitsAndBytesConfig"):
            setattr(transformers, name, object)
        stubs["transformers"] = transformers
    with mock.patch.dict(sys.modules, stubs):
        return (importlib.import_module("DataFactory"),
                importlib.import_module("util.data").Samples)


factory_module, Samples = _import_data_factory()
DataFactory = factory_module.DataFactory
SkillDataset = factory_module.SkillDataset


class SelectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data_dir = Path(temporary.name)
        for index in range(100):
            directory = self.data_dir / f"skill_{index:03d}"
            directory.mkdir()
            suffix = "\n" if index % 2 else ""
            (directory / "SKILL.md").write_text(
                f"---\nname: skill_{index}\n---\nUnique content {index}{suffix}",
                encoding="utf-8",
            )
        self.factory = DataFactory()
        self.factory._creator["fixture"] = partial(SkillDataset, data_dir=self.data_dir)

    def get(self, train=True, num=None, **kwargs):
        return self.factory.get_dataset("fixture", train=train, num=num, **kwargs)

    @staticmethod
    def paths(dataset):
        return [row["path"] for row in dataset.sample_metadata]

    def test_fixed_30_70_split_and_prefix_selection(self):
        original_order = sorted(self.data_dir.rglob("SKILL.md"))
        random.Random(0).shuffle(original_order)
        train = self.get(train=True)
        test = self.get(train=False)
        self.assertEqual(self.paths(train), [str(p.resolve()) for p in original_order[:30]])
        self.assertEqual(self.paths(test), [str(p.resolve()) for p in original_order[30:]])
        self.assertEqual(self.paths(self.get(num=3)), self.paths(train)[:3])
        self.assertEqual(self.paths(self.get(train=False, num=3)), self.paths(test)[:3])
        self.assertEqual([row["pool_index"] for row in train.sample_metadata], list(range(30)))
        self.assertEqual([row["pool_index"] for row in test.sample_metadata], list(range(70)))
        self.factory.validate_split(train, test)

    def test_default_selection_stays_at_sixteen(self):
        self.assertEqual(len(SkillDataset(True, data_dir=self.data_dir)), 16)
        self.assertEqual(len(SkillDataset(False, data_dir=self.data_dir)), 16)

    def test_text_template_and_content_hash_match_actual_model_input(self):
        pool = self.get()
        self.assertEqual(pool.template.prefix_1, "")
        self.assertEqual(pool.template.prefix_2, "")
        self.assertEqual(pool.template.format_trigger("trigger"), "trigger\n")
        for content, metadata in zip(pool, pool.sample_metadata):
            raw = Path(metadata["path"]).read_text(encoding="utf-8")
            self.assertEqual(content, raw if raw.endswith("\n") else raw + "\n")
            self.assertEqual(metadata["content_sha256"], hashlib.sha256(content.encode()).hexdigest())

    def test_seed_reproduces_selection_despite_global_random_state(self):
        pool = self.get()
        random.seed(742)
        first = pool.sample(num=8, seed=2)
        random.seed(941)
        for _ in range(100):
            random.random()
        second = self.get().sample(num=8, seed=2)
        direct = self.get(num=8, seed=2)
        self.assertEqual(first.sample_metadata, second.sample_metadata)
        self.assertEqual(first.sample_metadata, direct.sample_metadata)
        self.assertEqual(list(first), list(second))

    def test_sampling_does_not_mutate_global_rng_or_loaded_pool(self):
        pool = self.get()
        metadata_before = copy.deepcopy(pool.sample_metadata)
        contents_before = list(pool)
        state_before = random.getstate()
        selected = pool.sample(num=5, seed=4)
        self.assertEqual(state_before, random.getstate())
        self.assertEqual(metadata_before, pool.sample_metadata)
        self.assertEqual(contents_before, list(pool))
        selected.sample_metadata[0]["path"] = "changed"
        selected.dataset[0]["content"] = "changed"
        self.assertEqual(metadata_before, pool.sample_metadata)
        self.assertEqual(contents_before, list(pool))

    def test_each_of_five_seeds_samples_without_replacement_from_train_pool(self):
        pool = self.get()
        test = self.get(train=False, num=7)
        train_paths = set(self.paths(pool))
        test_paths = set(self.paths(test))
        selections = []
        for seed in range(5):
            selected = pool.sample(num=3, seed=seed)
            paths = self.paths(selected)
            self.assertEqual(len(paths), 3)
            self.assertEqual(len(set(paths)), 3)
            self.assertTrue(set(paths) <= train_paths)
            self.assertTrue(set(paths).isdisjoint(test_paths))
            self.assertEqual([pool[row["pool_index"]] for row in selected.sample_metadata], list(selected))
            self.factory.validate_split(selected, test)
            selections.append(tuple(paths))
        self.assertEqual(len(set(selections)), 5)

    def test_testset_is_fixed_across_train_sizes_and_seeds(self):
        baseline = self.get(train=False, num=7)
        expected_metadata = copy.deepcopy(baseline.sample_metadata)
        expected_contents = list(baseline)
        pool = self.get()
        for number in (1, 3, 5, 8, 16):
            for seed in range(5):
                pool.sample(num=number, seed=seed)
                reloaded = self.get(train=False, num=7)
                self.assertEqual(reloaded.sample_metadata, expected_metadata)
                self.assertEqual(list(reloaded), expected_contents)
                self.assertEqual(baseline.sample_metadata, expected_metadata)

    def test_invalid_requested_counts_fail_instead_of_silently_truncating(self):
        for train, size in ((True, 30), (False, 70)):
            for count in (0, -1, size + 1, 1.5, True, "3"):
                with self.subTest(train=train, count=count):
                    with self.assertRaises(ValueError):
                        self.get(train=train, num=count)
        pool = self.get()
        for count in (None, 0, -1, 31, 1.5, True, "3"):
            with self.subTest(sample_count=count):
                with self.assertRaises(ValueError):
                    pool.sample(num=count, seed=0)

    def test_empty_pool_is_an_explicit_error(self):
        with tempfile.TemporaryDirectory() as directory:
            for train in (True, False):
                for count in (None, 1):
                    with self.subTest(train=train, count=count):
                        with self.assertRaisesRegex(ValueError, "pool is empty"):
                            SkillDataset(train, num=count, data_dir=directory)

    def test_seed_is_integer_and_sampling_is_train_only(self):
        for seed in (None, True, 1.5, "0"):
            with self.subTest(seed=seed):
                with self.assertRaises(ValueError):
                    self.get().sample(num=3, seed=seed)
        with self.assertRaises(ValueError):
            self.get(train=False).sample(num=3, seed=0)
        with self.assertRaises(ValueError):
            self.get(train=False, num=3, seed=0)

    def test_validate_split_rejects_wrong_pool_roles(self):
        with self.assertRaises(ValueError):
            self.factory.validate_split(self.get(train=False), self.get())

    def test_validate_split_rejects_duplicate_paths_within_either_split(self):
        for duplicated_train in (True, False):
            train, test = self.get(), self.get(train=False)
            target = train if duplicated_train else test
            target.sample_metadata[1]["path"] = target.sample_metadata[0]["path"]
            with self.subTest(train=duplicated_train):
                with self.assertRaisesRegex(ValueError, "Duplicate.*path"):
                    self.factory.validate_split(train, test)

    def test_validate_split_rejects_paths_shared_between_splits(self):
        train, test = self.get(), self.get(train=False)
        test.sample_metadata[0]["path"] = train.sample_metadata[0]["path"]
        with self.assertRaisesRegex(ValueError, "leakage.*path"):
            self.factory.validate_split(train, test)

    def test_validate_split_rejects_duplicate_content_at_different_paths(self):
        original = self.get()
        source, destination = self.paths(original)[:2]
        Path(destination).write_text(Path(source).read_text(encoding="utf-8"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate.*content_sha256"):
            self.factory.validate_split(self.get(), self.get(train=False))

    def test_validate_split_rejects_duplicate_content_in_test_pool(self):
        original = self.get(train=False)
        source, destination = self.paths(original)[:2]
        Path(destination).write_text(Path(source).read_text(encoding="utf-8"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate.*content_sha256"):
            self.factory.validate_split(self.get(), self.get(train=False))

    def test_validate_split_rejects_cross_split_content_with_newline_difference(self):
        train, test = self.get(), self.get(train=False)
        source = Path(self.paths(train)[0])
        destination = Path(self.paths(test)[0])
        destination.write_text(source.read_text(encoding="utf-8").rstrip("\n"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "leakage.*content_sha256"):
            self.factory.validate_split(self.get(), self.get(train=False))

    def test_legacy_samples_keep_original_api_but_reject_new_experiment_api(self):
        legacy = Samples(train=True, num=3, data_dir=self.data_dir)
        self.assertIsInstance(legacy, Samples)
        self.assertNotIsInstance(legacy, SkillDataset)
        self.assertEqual(len(legacy), 3)
        for name in ("Samples", "Financial", "Tomatoes", "SQuAD", "Roles", "Awesome", "SIQA"):
            for kwargs in ({"num": None}, {"num": 3, "seed": 0}):
                with self.subTest(dataset=name, kwargs=kwargs):
                    with self.assertRaisesRegex(ValueError, "Unknown dataset"):
                        self.factory.get_dataset(name, train=True, **kwargs)
        with self.assertRaises(ValueError):
            self.factory.validate_split(legacy, self.get(train=False))

    def test_unknown_dataset_is_an_explicit_error(self):
        for name in ("missing_category", "documents_3_shots", "shots"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "Unknown dataset"):
                    self.factory.get_dataset(name, train=True, num=None)


class ExpandedCategoryTests(unittest.TestCase):
    def setUp(self):
        previous = Path.cwd()
        os.chdir(REPOSITORY_ROOT)
        self.addCleanup(os.chdir, previous)
        self.factory = DataFactory()

    def test_all_eleven_english_categories_have_independent_pools(self):
        expected_sizes = {
            "documents": 100,
            "data_analysis": 100,
            "software_development": 100,
            "information_retrieval": 100,
            "workflow": 100,
            "content_creation": 100,
            "scientific_research": 100,
            "security": 100,
            "cloud": 100,
            "marketing": 100,
            "product_management": 100,
        }
        self.assertEqual(set(factory_module.SKILL_CATEGORIES), set(expected_sizes))
        all_paths = set()
        for alias in factory_module.SKILL_CATEGORIES:
            category = alias
            with self.subTest(dataset=alias):
                category_root = REPOSITORY_ROOT / "data/skill_expansion_20260922/samples" / category
                train = self.factory.get_dataset(alias, train=True, num=None)
                test = self.factory.get_dataset(alias, train=False, num=None)
                self.assertEqual(len(train) + len(test), expected_sizes[alias])
                self.assertEqual(len(train), int(expected_sizes[alias] * 0.3))
                self.factory.validate_split(train, test)
                paths = {row["path"] for row in train.sample_metadata + test.sample_metadata}
                self.assertTrue(all(Path(path).is_relative_to(category_root) for path in paths))
                self.assertTrue(paths.isdisjoint(all_paths))
                all_paths.update(paths)
                translated = self.factory.get_dataset(category, train=True, num=None)
                self.assertEqual(translated.sample_metadata, train.sample_metadata)
                for seed in range(5):
                    selected = train.sample(num=3, seed=seed)
                    self.assertEqual(len(selected), 3)
                    self.factory.validate_split(selected, test)

    def test_non_english_and_legacy_names_are_not_registered(self):
        for name in ("01_文档处理", "文档处理", "WebTesting", "webtesting", "Samples"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "Unknown dataset"):
                    self.factory.get_dataset(name, train=True, num=None)


if __name__ == "__main__":
    unittest.main()
