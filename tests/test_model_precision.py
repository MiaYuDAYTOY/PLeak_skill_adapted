"""Verify precision overrides at the loader boundary without loading weights."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

try:
    import torch
except ImportError:
    torch = None


@unittest.skipIf(torch is None, 'PyTorch dtype objects are required')
class ModelPrecisionTests(unittest.TestCase):
    def setUp(self):
        transformers = types.ModuleType('transformers')
        transformers.AutoTokenizer = Mock()
        self.loader = Mock()
        self.model = Mock()
        self.model.eval.return_value = self.model
        self.loader.from_pretrained.return_value = self.model
        transformers.AutoModelForCausalLM = self.loader
        source = Path(__file__).resolve().parents[1] / 'ModelFactory.py'
        spec = importlib.util.spec_from_file_location('factory_precision_test', source)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'transformers': transformers}):
            spec.loader.exec_module(module)
        self.factory = module.ModelFactory()

    def test_default_loading_options_are_unchanged(self):
        self.assertIs(self.factory.get_model('llama'), self.model)
        self.assertEqual(self.loader.from_pretrained.call_args.kwargs, {
            'device_map': 'auto', 'load_in_4bit': True,
            'bnb_4bit_compute_dtype': torch.float16, 'local_files_only': True,
        })
        self.assertFalse(self.model.config.use_cache)

    def test_bf16_override_sets_both_compute_and_model_precision(self):
        self.factory.get_model('llama', compute_dtype=torch.bfloat16)
        options = self.loader.from_pretrained.call_args.kwargs
        self.assertIs(options['bnb_4bit_compute_dtype'], torch.bfloat16)
        self.assertIs(options['torch_dtype'], torch.bfloat16)
        self.assertTrue(options['load_in_4bit'])
        self.assertTrue(options['local_files_only'])

    def test_invalid_override_fails_before_loading(self):
        with self.assertRaises(ValueError):
            self.factory.get_model('llama', compute_dtype='bfloat16')
        self.loader.from_pretrained.assert_not_called()


if __name__ == '__main__':
    unittest.main()
