import csv
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('regression_webtesting', ROOT / 'regression_webtesting.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RegressionSelectionTests(unittest.TestCase):
    def test_historical_selection_and_success_are_preserved(self):
        manifest = MODULE.prepare()
        self.assertEqual(manifest['historical_full_reproductions'], 17)
        self.assertEqual(len(manifest['train_samples']), 3)
        self.assertEqual(len(manifest['test_samples']), 20)
        self.assertEqual(len(manifest['trigger_ids']), 12)
        self.assertFalse({x['path'] for x in manifest['train_samples']} &
                         {x['path'] for x in manifest['test_samples']})

    def test_changed_test_order_is_rejected(self):
        with MODULE.REFERENCE.open(newline='', encoding='utf-8') as stream:
            reader = csv.DictReader(stream)
            fields, rows = reader.fieldnames, list(reader)
        rows[0], rows[1] = rows[1], rows[0]
        with tempfile.TemporaryDirectory() as temp:
            reference = Path(temp) / 'reference.csv'
            with reference.open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            shutil.copyfile(MODULE.REFERENCE.with_suffix('.trigger_ids.json'),
                            reference.with_suffix('.trigger_ids.json'))
            with self.assertRaisesRegex(ValueError, 'content/order mismatch'):
                MODULE.prepare(reference=reference)


@unittest.skipUnless(importlib.util.find_spec('torch'), 'torch not installed')
class GradientComparisonTests(unittest.TestCase):
    def test_reports_real_difference_and_candidate_overlap(self):
        import torch
        a, b = torch.tensor([[1., 2.]]), torch.tensor([[1., 3.]])
        result = MODULE.compare_gradients(a, b, [[1, 2]], [[2, 3]])
        self.assertEqual(result['max_absolute_difference'], 1.)
        self.assertFalse(result['allclose_rtol_1e-3_atol_1e-6'])
        self.assertEqual(result['top30_candidate_overlap_per_position'], [0.5])
        same = MODULE.compare_gradients(a, a, [[1, 2]], [[1, 2]])
        self.assertEqual(same['relative_l2_difference'], 0.)
        self.assertTrue(same['allclose_rtol_1e-3_atol_1e-6'])

    def test_zero_or_nonfinite_gradient_is_not_a_pass(self):
        import torch
        for bad in [torch.zeros(2), torch.tensor([float('nan'), 1.])]:
            with self.assertRaises(ValueError):
                MODULE.compare_gradients(bad, torch.ones(2), [[1]], [[1]])


if __name__ == '__main__':
    unittest.main()
