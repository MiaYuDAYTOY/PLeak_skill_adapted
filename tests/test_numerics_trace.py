"""Verify forward tracing detects the first bad operation without changing results."""
import contextlib
import io
from pathlib import Path
import sys
import unittest

try:
    import torch
except ImportError:
    torch = None

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if torch is not None:
    from util.numerics_trace import trace_forward_numerics

    class Attention(torch.nn.Module):
        def __init__(self, bad_probabilities=False):
            super().__init__()
            self.bad_probabilities = bad_probabilities

        def forward(self, x):
            scores = torch.matmul(x, x.transpose(-2, -1)) / 2
            probabilities = scores.float().softmax(-1).to(x.dtype)
            if self.bad_probabilities:
                probabilities = torch.full_like(probabilities, float('nan'))
            return torch.matmul(probabilities, x)

    class Model(torch.nn.Module):
        def __init__(self, bad_probabilities=False):
            super().__init__()
            self.self_attn = Attention(bad_probabilities)

        def forward(self, x):
            return self.self_attn(x)


@unittest.skipIf(torch is None, 'PyTorch is required for CPU numerics tests')
class NumericsTraceTests(unittest.TestCase):
    def test_finite_output_unchanged_and_hooks_removed(self):
        model = Model()
        x = torch.arange(8, dtype=torch.float32).reshape(1, 1, 2, 4) / 10
        expected = model(x)
        original_matmul = torch.matmul
        with contextlib.redirect_stdout(io.StringIO()), trace_forward_numerics(model):
            actual = model(x)
        torch.testing.assert_close(actual, expected, rtol=0, atol=0)
        self.assertIs(torch.matmul, original_matmul)
        self.assertFalse(model.self_attn._forward_hooks)
        self.assertFalse(model.self_attn._forward_pre_hooks)

    def test_fp16_qk_overflow_stops_before_softmax_and_restores_matmul(self):
        model = Model()
        x = torch.full((1, 1, 2, 4), 300, dtype=torch.float16)
        original_matmul = torch.matmul
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(FloatingPointError, 'QK before scaling output'):
                with trace_forward_numerics(model):
                    model(x)
        self.assertIn('min=300.0 max=300.0', output.getvalue())
        self.assertIn('max=inf', output.getvalue())
        self.assertIs(torch.matmul, original_matmul)
        self.assertFalse(model.self_attn._forward_hooks)
        self.assertFalse(model.self_attn._forward_pre_hooks)

    def test_bad_probabilities_identified_before_second_matmul(self):
        model = Model(bad_probabilities=True)
        x = torch.ones((1, 1, 2, 4))
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(FloatingPointError, 'attention matmul 2 left input'):
                with trace_forward_numerics(model):
                    model(x)

    def test_nan_module_output_is_identified(self):
        model = torch.nn.Module()
        model.add_module('q_proj', torch.nn.Identity())
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(FloatingPointError, 'q_proj output'):
                with trace_forward_numerics(model):
                    model.q_proj(torch.tensor([float('nan')]))
        self.assertFalse(model.q_proj._forward_hooks)

    def test_fp16_gated_product_overflow_is_caught_before_down_projection(self):
        model = torch.nn.Module()
        model.add_module('down_proj', torch.nn.Identity())
        gate = torch.tensor([347.25], dtype=torch.float16)
        up = torch.tensor([361.25], dtype=torch.float16)
        product = torch.nn.functional.silu(gate) * up
        self.assertTrue(torch.isfinite(gate).all())
        self.assertTrue(torch.isfinite(up).all())
        self.assertTrue(torch.isinf(product).all())
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(FloatingPointError, r'down_proj input \(gated product\)'):
                with trace_forward_numerics(model):
                    model.down_proj(product)
        self.assertFalse(model.down_proj._forward_pre_hooks)

    def test_bf16_gated_product_stays_finite_at_same_magnitude(self):
        model = torch.nn.Module()
        model.add_module('down_proj', torch.nn.Identity())
        gate = torch.tensor([347.25], dtype=torch.bfloat16)
        up = torch.tensor([361.25], dtype=torch.bfloat16)
        product = torch.nn.functional.silu(gate) * up
        with contextlib.redirect_stdout(io.StringIO()), trace_forward_numerics(model):
            result = model.down_proj(product)
        self.assertTrue(torch.isfinite(result).all())


if __name__ == '__main__':
    unittest.main()
