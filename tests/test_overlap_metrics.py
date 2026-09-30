"""CPU-only metric checks; no model weights or optional ML stack required."""

import ast
import contextlib
import csv
import io
import json
import random
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from main import save_group_summary
from util.overlap_metrics import (
    OVERLAP_FIELDS, longest_common_subsequence_length, rouge_overlap,
    strip_yaml_front_matter,
)


def sampler_evaluator():
    # Load the real evaluator methods without importing CUDA/model dependencies.
    tree = ast.parse((Path(__file__).resolve().parents[1] / "Sampler.py").read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == "Sampler")
    keep = {"normalize_markdown", "content_token_ids",
            "longest_common_prefix_length", "evaluate_skill_leakage"}
    cls.body = [node for node in cls.body if getattr(node, "name", None) in keep]
    namespace = dict(Counter=Counter, json=json, OVERLAP_FIELDS=OVERLAP_FIELDS,
                     rouge_overlap=rouge_overlap, strip_yaml_front_matter=strip_yaml_front_matter)
    exec(compile(ast.Module(body=[cls], type_ignores=[]), "Sampler.py", "exec"), namespace)
    sampler = namespace["Sampler"]()

    class CharacterTokenizer:
        all_special_ids = [-1]

        def encode(self, text, add_special_tokens=False):
            assert not add_special_tokens
            return [ord(char) for char in text]

    sampler.tokenizer = CharacterTokenizer()
    return sampler


class OverlapTests(unittest.TestCase):
    def test_edits_and_repetition(self):
        scores = rouge_overlap(list("ABCDE"), list("ABXDE"))
        self.assertEqual(scores, {"rougeL_recall": .8, "rougeL_precision": .8,
                                  "rouge2_recall": .5})
        self.assertEqual(rouge_overlap(list("ABCDE"), list("ABCDEABCDE")),
                         {"rougeL_recall": 1., "rougeL_precision": .5,
                          "rouge2_recall": 1.})
        self.assertEqual(rouge_overlap(list("AAAAB"), list("AAAAAAAA"))["rouge2_recall"], .75)

    def test_order_empty_and_single_token(self):
        self.assertEqual(rouge_overlap([1, 2, 3], [3, 2, 1])["rougeL_recall"], 1 / 3)
        for reference, prediction in [([], []), ([1], []), ([], [1]), ([1], [2])]:
            self.assertTrue(all(value == 0 for value in rouge_overlap(reference, prediction).values()))
        self.assertEqual(rouge_overlap([1], [1])["rouge2_recall"], 0)

    def test_lcs_against_independent_dp(self):
        rng = random.Random(7)
        for _ in range(300):
            a = [rng.randrange(5) for _ in range(rng.randrange(30))]
            b = [rng.randrange(5) for _ in range(rng.randrange(30))]
            row = [0] * (len(b) + 1)
            for x in a:
                prev = row
                row = [0]
                for j, y in enumerate(b):
                    row.append(prev[j] + 1 if x == y else max(prev[j + 1], row[-1]))
            self.assertEqual(longest_common_subsequence_length(a, b), row[-1])

    def test_front_matter(self):
        self.assertEqual(strip_yaml_front_matter("---\n# comment\nname: demo\n---\n\n# Body\n中文"), "# Body\n中文")
        self.assertEqual(strip_yaml_front_matter("---\nname: demo\n...\nABC"), "ABC")
        self.assertEqual(strip_yaml_front_matter("---\nname: demo\n---"), "")
        for text in ["---\n\n# Body\n---\nABC", "---\nname: demo\nABC", "# Body", ""]:
            self.assertEqual(strip_yaml_front_matter(text), text)

    def test_evaluator_body_failed_samples_and_legacy_metrics(self):
        evaluator = sampler_evaluator()
        target = "---\r\nname: demo\r\n---\r\nABCDE"
        results = [
            dict(context=target, generation="ABCDEABCDE", status="ok",
                 sample_index=12, sample_path="demo/SKILL.md", ended_with_eos=False),
            dict(context="ABCDE", generation="ABCDE", status="ok", ended_with_eos=True),
            dict(context="ignored", generation="", status="generation_failed"),
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            report = evaluator.evaluate_skill_leakage(results)
        self.assertEqual((report["total_samples"], report["evaluated_samples"], report["failed_samples"]), (3, 2, 1))
        first = report["samples"][0]
        self.assertEqual(first["index"], 12)
        self.assertEqual(first["sample_path"], "demo/SKILL.md")
        self.assertEqual(first["body_rougeL_recall"], 1)
        self.assertEqual(first["body_rougeL_precision"], .5)
        self.assertEqual(first["body_rouge2_recall"], 1)
        self.assertLess(first["rougeL_recall"], first["body_rougeL_recall"])
        self.assertEqual(report["mean_body_rougeL_precision"], .75)
        self.assertEqual(report["full_skill_leak_count"], 1)
        for field in ["full_skill_leak_rate", "exact_markdown_match_rate",
                      "exact_token_match_rate", "mean_common_prefix_ratio", "eos_rate"]:
            self.assertEqual(report[field], .5)
        with contextlib.redirect_stdout(io.StringIO()):
            stripped = evaluator.evaluate_skill_leakage([
                dict(context=target, generation="---\nname: different\n---\nABCDE")])
        self.assertEqual(stripped["mean_body_rougeL_recall"], 1)
        self.assertEqual(stripped["mean_body_rougeL_precision"], 1)
        for cases in [[], [results[-1]], [dict(context="ABCDE", generation="")]]:
            with contextlib.redirect_stdout(io.StringIO()):
                empty = evaluator.evaluate_skill_leakage(cases)
            self.assertTrue(all(empty["mean_" + field] == 0 for field in OVERLAP_FIELDS))

    def test_cross_seed_summary_serialization(self):
        runs = []
        for sample in [0, 1]:
            for attack in [0, 1]:
                runs.append(dict(dataset="documents", train_num=3, prefix_length=8,
                                 test_num=2, token_length=12, shadow_model="llama",
                                 target_model="llama", sample_seed=sample, attack_seed=attack,
                                 metrics={"evaluated_samples": 2, **{
                                     "mean_" + name: (sample + attack) / 2
                                     for name in OVERLAP_FIELDS}}))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "group.summary.json"
            with contextlib.redirect_stdout(io.StringIO()):
                save_group_summary(path, runs, [0, 1], [0, 1])
            summary = json.loads(path.read_text())
            self.assertEqual(summary["overall_mean"]["metric_means"]["mean_body_rougeL_recall"], .5)
            self.assertEqual(summary["mean_over_attack_seeds"][0]["metric_means"]["mean_rougeL_recall"], .25)
            with path.with_suffix(".csv").open() as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 5)
            self.assertTrue(all("mean_" + field in rows[0] for field in OVERLAP_FIELDS))


if __name__ == "__main__":
    unittest.main()
