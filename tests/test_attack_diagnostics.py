"""CPU regression tests: no model downloads or CUDA required."""
import importlib.util
import contextlib
import io
import math
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

try:
    import torch
    import numpy as np
except ImportError:
    torch = None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if torch is not None:
    factory_stub = types.ModuleType('ModelFactory')
    factory_stub.ModelFactory = object
    spec = importlib.util.spec_from_file_location('attack_under_test', ROOT / 'Attack.py')
    attack_module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'ModelFactory': factory_stub}):
        spec.loader.exec_module(attack_module)
    HotFlip = attack_module.HotFlip
    from util.template import TextTemplate

    class Tokenizer:
        def encode(self, text, add_special_tokens=True):
            return ([1] if add_special_tokens else []) + [ord(c) for c in text]

        def decode(self, ids, **kwargs):
            return ''.join(chr(int(i)) for i in ids)

    class BadGradient(torch.autograd.Function):
        @staticmethod
        def forward(ctx, value):
            return value.clone()

        @staticmethod
        def backward(ctx, gradient):
            return gradient * float('nan')

    class TinyLM(torch.nn.Module):
        def __init__(self, failure=None):
            super().__init__()
            self.embedding = torch.nn.Embedding(256, 4)
            self.head = torch.nn.Linear(4, 256)
            self.failure = failure
            self.backward_calls = 0
            self.grad_modes = []

        def get_input_embeddings(self):
            return self.embedding

        def forward(self, input_ids=None, inputs_embeds=None, labels=None, **kwargs):
            self.grad_modes.append(torch.is_grad_enabled())
            x = self.embedding(input_ids) if inputs_embeds is None else inputs_embeds
            if self.failure == 'gradient':
                x = BadGradient.apply(x)
            logits = self.head(x.cumsum(dim=1))
            loss = torch.nn.functional.cross_entropy(logits[:, :-1].reshape(-1, 256),
                                                      labels[:, 1:].reshape(-1))
            if self.failure == 'forward':
                loss = loss * float('nan')
            if loss.requires_grad:
                loss.register_hook(self.record_backward)
            return (loss,)

        def record_backward(self, gradient):
            self.backward_calls += 1
            return gradient


@unittest.skipIf(torch is None, 'PyTorch and NumPy are required for CPU gradient tests')
class AttackDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(3)
        self.attack = HotFlip.__new__(HotFlip)
        self.attack.model = TinyLM()
        self.attack.tokenizer = Tokenizer()
        self.attack.template = TextTemplate('', '')
        self.attack.user_prefix = ''
        self.attack.device = torch.device('cpu')
        self.attack.prefix_length = 2
        self.attack.trigger_tokens = np.array([97, 98])
        self.attack.embedding_weight = self.attack.get_embedding_weight()

    def test_input_keeps_full_context_but_only_prefix_continuation(self):
        a = self.attack
        text = 'a long secret\n'
        inputs, labels, start, end = a.make_target(0, 0, text, a.trigger_tokens)
        prompt = a.tokenizer.encode(text + 'ab\n')
        self.assertEqual(inputs.tolist(), [prompt + [ord('a'), ord(' ')]])
        self.assertEqual(labels.tolist(), [[-100] * len(prompt) + [ord('a'), ord(' ')]])
        self.assertEqual(inputs[0, start:end].tolist(), [97, 98])

    def test_finite_loss_and_gradient_match_original_objective_and_own_storage(self):
        a = self.attack
        texts = ['secret\n', 'another\n']
        expected_loss = 0.
        expected_gradient = torch.zeros(2, 4)
        for i, text in enumerate(texts):
            ids, labels, start, end = a.make_target(i, 0, text, a.trigger_tokens)
            x = a.model.get_input_embeddings()(ids).detach().requires_grad_(True)
            loss = a.model(inputs_embeds=x, labels=labels)[0] / len(texts)
            expected_loss += loss.item()
            expected_gradient += torch.autograd.grad(loss, x)[0][0, start:end]
        actual_loss, gradient = a.compute_loss(texts, a.trigger_tokens, 0, require_grad=True)
        self.assertAlmostEqual(actual_loss, expected_loss)
        torch.testing.assert_close(gradient, expected_gradient)
        self.assertIsNone(gradient.grad_fn)
        self.assertEqual(gradient.untyped_storage().nbytes(), gradient.numel() * gradient.element_size())

    def test_nonfinite_forward_stops_before_backward(self):
        self.attack.model = TinyLM('forward')
        with self.assertRaisesRegex(FloatingPointError, 'sample 0.*forward loss'):
            self.attack.compute_loss(['secret\n'], self.attack.trigger_tokens, 0, True)
        self.assertEqual(self.attack.model.backward_calls, 0)

    def test_finite_forward_but_bad_backward_is_reported_as_gradient(self):
        self.attack.model = TinyLM('gradient')
        with self.assertRaisesRegex(FloatingPointError, 'sample 0.*trigger gradient'):
            self.attack.compute_loss(['secret\n'], self.attack.trigger_tokens, 0, True)
        self.assertEqual(self.attack.model.backward_calls, 1)

    def test_candidate_evaluation_disables_grad_without_callers_context(self):
        loss, gradient = self.attack.compute_loss(['secret\n'], self.attack.trigger_tokens, 0, False)
        self.assertTrue(math.isfinite(loss))
        self.assertIsNone(gradient)
        self.assertEqual(self.attack.model.grad_modes, [False])

    def test_empty_supervision_stops_before_forward(self):
        self.attack.prefix_length = 0
        with self.assertRaisesRegex(ValueError, 'no supervised tokens'):
            self.attack.compute_loss(['secret\n'], self.attack.trigger_tokens, 0, True)
        self.assertEqual(self.attack.model.grad_modes, [])

    def test_oom_identifies_sample_and_forward_even_without_debug(self):
        output = io.StringIO()
        with patch.dict('os.environ', {'PLEAK_DEBUG': '0'}), \
             patch.object(self.attack.model, 'forward', side_effect=torch.cuda.OutOfMemoryError('test')), \
             contextlib.redirect_stdout(output):
            with self.assertRaises(torch.cuda.OutOfMemoryError):
                self.attack.compute_loss(['secret\n'], self.attack.trigger_tokens, 0, True)
        self.assertIn('OOM sample 0', output.getvalue())
        self.assertIn('stage=forward seq_len=', output.getvalue())

    def test_bad_score_is_rejected_before_topk(self):
        self.attack.embedding_weight = torch.full((256, 4), float('inf'))
        with self.assertRaisesRegex(FloatingPointError, 'candidate scores'):
            self.attack.hotflip_attack(torch.ones(2, 4))

    def test_nan_candidate_cannot_update_trigger(self):
        a = self.attack
        before = a.trigger_tokens.copy()
        with patch.object(a, 'compute_loss', side_effect=[(1., torch.ones(2, 4)), (float('nan'), None)]), \
             patch.object(a, 'hotflip_attack', return_value=np.array([[99], [100]])):
            with self.assertRaisesRegex(FloatingPointError, 'stopping before trigger update'):
                a.replace_triggers(['secret\n'])
        np.testing.assert_array_equal(a.trigger_tokens, before)


if __name__ == '__main__':
    unittest.main()
